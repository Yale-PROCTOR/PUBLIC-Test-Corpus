// © 2026 Massachusetts Institute of Technology
// MIT License

//! The `candidate` macro is the main feature of this library.
//!
//! It allows you to write a test harness for a candidate like so:
//!
//! ```ignore
//! harness! {
//!     state: {
//!         foo: bool,
//!         bar: Vec<c_char>,
//!         returns: i32
//!     },
//!
//!     signature: extern "C" fn(bool, *mut c_char) -> i32,
//!
//!     fn run(&mut self) {
//!         self.returns = unsafe {
//!             (*SYMBOL)(
//!                 self.foo,
//!                 self.bar.as_mut_ptr()
//!             )
//!         };
//!     }
//! }
//! ```
//!
//! The `state` argument defines the state that is reachable from
//! the input parameters to the candidate, as well as the return value.
//!
//! The `signature` defines how the dynamically-linked symbol will be called.
//!
//! The `run` function does the work of calling the symbol,
//! and the `self` parameter is an instance of the state defined previously.
//!
//! The macro generates a `main` function that automatically provides the
//! program with a command-line interface for running the harness.
//! See the documentation for `invoke_cli` for information on how to use it.

// TODO: crate features

// The `candidate` macro generates code that uses the following items internally.
// In order to make using this crate easy, this library re-exports all of them
// so that users can do `use cando::*;` to easily get all of them.
pub use {
    arbitrary::{self, Arbitrary, Unstructured},
    argh,
    getrandom,
    libloading::{Library, Symbol},
    serde::{self, Deserialize, Serialize},
    serde_json::{from_str, to_string_pretty},
    std::{
        // In contrast to the other re-exports,
        // these are re-exported for the convenience of defining the `state`.
        ffi::*,
        path::{Path, PathBuf},
        sync::{LazyLock, OnceLock},
    },
};

#[macro_export]
macro_rules! state_member {
    ($struc:item) => {
        #[repr(C)]
        #[derive(Debug, Clone, Arbitrary, Serialize, Deserialize, PartialEq)]
        #[serde(crate = "self::serde")]
        $struc
    };
}

/// The harness macro has two forms.
///
/// If you're using the standardized naming where every candidate's shared library
/// filename and symbol name are identical to the candidate itself,
/// then you can use the short form,
/// without the explicit `library` and `symbol` arguments:
///
/// ```ignore
/// harness! {
///     state: { foo: i32 },
///     signature: extern "C" fn(),
///     fn run(&mut self) {}
/// }
/// ```
///
/// If you're not using standardized naming,
/// then specify the shared library filename and symbol name as follows:
///
/// ```ignore
/// harness! {
///     state: { foo: i32 },
///     library: "hello",
///     symbol: "my_hello",
///     signature: extern "C" fn(),
///     fn run(&mut self) {}
/// }
/// ```
///
/// NOTE: for the `library` argument,
/// if attempting to link "libfoo.so",
/// the argument should be "foo",
/// including neither the "lib" prefix nor the file extension.
#[macro_export]
macro_rules! harness {
    {
        state: {
            $(
                $field: ident: $typ: ty
            ),* $(,)?
        },

        signature: $sig:ty,

        $run_fn:item
    } => {

        harness! {
            state: { $($field : $typ),* },
            library: CANDIDATE_NAME,
            symbol: CANDIDATE_SYMBOL_NAME,
            signature: $sig,
            $run_fn
        }

    };

    {
        state: {
            $(
                $field: ident: $typ: ty
            ),* $(,)?
        },

        library: $lib:expr,

        symbol: $sym:expr,

        signature: $sig:ty,

        $run_fn:item
    } => {
        #[cfg(not(fuzzing))]
        fn main() {
            conduct();
        }

        #[cfg(fuzzing)]
        libfuzzer_sys::fuzz_target!(|input: State| {
            let mut state = input;
            state.run();
        });


        #[cfg(target_os = "macos")]
        pub fn get_lib_name(stem: &str) -> String {
            format!("lib{}.dylib", stem)
        }

        #[cfg(target_os = "linux")]
        pub fn get_lib_name(stem: &str) -> String {
            format!("lib{}.so", stem)
        }

        /// This function provides a convenient entry point
        /// for using this crate as a CLI tool.
        pub fn conduct() {
           let args: Vec<String> = std::env::args().collect();
           let slice: Vec<&str> = args.iter().map(|e| &**e).collect();
           let exit_code = conduct_with(&slice);
           std::process::exit(exit_code);
        }

        pub fn conduct_with(raw_args: &[&str]) -> i32 {
            use argh::FromArgs;

            /// Tool for running test cases for translation candidates
            #[derive(Debug, FromArgs)]
            struct TopLevelOptions {
                #[argh(subcommand)]
                subcommand: TopLevelSubcommand
            }

            #[derive(Debug, FromArgs)]
            #[argh(subcommand)]
            enum TopLevelSubcommand {
                Lib(LibOptions),
                Bin(BinOptions),
            }

            /// Run tests for a library candidate
            #[derive(Debug, FromArgs)]
            #[argh(subcommand, name="lib")]
            struct LibOptions {
                /// execute the candidate using a zeroed state
                #[argh(switch, short='z')]
                zero: bool,

                /// print verbose output
                #[argh(switch, short='v')]
                verbose: bool,

                /// print json output
                #[argh(switch, short='j')]
                json: bool,

                /// suppress ordinary output
                #[argh(switch, short='q')]
                quiet: bool,

                /// print the difference for failing equality
                #[argh(switch, short='d')]
                diff: bool,

                /// execute the candidate using a pattern of the specified length
                #[argh(option, short='p')]
                pattern: Option<usize>,

                /// execute the candidate using random bytes of the specified length
                #[argh(option, short='r')]
                random: Option<usize>,

                /// write JSON test vector to file
                #[argh(option, short='w')]
                write: Option<String>,

                /// execute the candidate using a file produced by cargo-fuzz, path relative to runner dir
                #[argh(option, short='f')]
                fuzzed: Option<String>,

                /// run one or more specific test cases
                #[argh(option, short='c')]
                case: Vec<String>,
            }

            /// Run tests for a binary candidate
            #[derive(Debug, FromArgs)]
            #[argh(subcommand, name="bin")]
            struct BinOptions {}

            let opts = match TopLevelOptions::from_args(&[raw_args[0]], &raw_args[1..]) {
                Ok(a) => a,
                Err(e) => {
                    eprintln!("{}", e.output);
                    return 1;
                }
            };

            let exit_code = match opts.subcommand {
                TopLevelSubcommand::Lib(lopts) => {
                    let _ = DIFF_FLAG.set(lopts.diff);
                    let mut tcs = std::collections::HashMap::new();
                    let mut json_string = String::new();

                    if lopts.zero {
                        let mut state = State::zeroed();

                        json_string.push_str(&format!("{{ \"lib_state_in\": {},", state.to_json()));
                        state.run();
                        json_string.push_str(&format!("\"lib_state_out\": {} }}", state.to_json()));
                    } else if let Some(pattern_len) = lopts.pattern {
                        let bytes = vec![85; pattern_len];
                        let mut state = State::from_bytes(&bytes);
                        json_string.push_str(&format!("{{ \"lib_state_in\": {},", state.to_json()));
                        state.run();
                        json_string.push_str(&format!("\"lib_state_out\": {} }}", state.to_json()));
                    } else if let Some(random_len) = lopts.random {
                        let mut bytes = vec![0; random_len];
                        getrandom::fill(&mut bytes).unwrap();
                        let mut state = State::from_bytes(&bytes);
                        json_string.push_str(&format!("{{ \"lib_state_in\": {},", state.to_json()));
                        state.run();
                        println!("lib_state_out: {}", state.to_json());
                        json_string.push_str(&format!("\"lib_state_out\": {} }}", state.to_json()));
                    } else if let Some(filename) = lopts.fuzzed {
                        let mut path = RUNNER_DIR.clone();
                        path.push(filename);
                        let bytes = std::fs::read(path).unwrap();
                        let mut state = State::from_bytes(bytes.as_slice());
                        json_string.push_str(&format!("{{ \"lib_state_in\": {},", state.to_json()));
                        if lopts.verbose {
                            println!("{}", state.to_json());
                        }
                        state.run();
                        json_string.push_str(&format!("\"lib_state_out\": {} }}", state.to_json()));
                    } else if lopts.case.is_empty() {
                        tcs = TestCase::load_all();
                    } else {
                        for case in lopts.case {
                            let tc = TestCase::from_corpus(&case);
                            tcs.insert(case, tc);
                        }
                    }

                    if lopts.json {
                        println!("{}", json_string);
                    }

                    let mut report = std::collections::HashMap::new();

                    for (case, tc) in tcs {
                        let mut state = tc.lib_state();

                        if lopts.verbose {
                            println!("case: {}", case);
                            println!("in: {:#?}", tc.lib_state());
                            println!("expected out: {:#?}", tc.lib_state_out);
                        }

                        json_string.push_str(&format!("{{ \"lib_state_in\": {},", state.to_json()));
                        state.run();
                        json_string.push_str(&format!("\"lib_state_out\": {} }}", state.to_json()));

                        let result = tc.equals_expected(&state);
                        report.insert(case, result);

                        if lopts.json {
                            println!("{}", state.to_json());
                        }

                        if lopts.verbose {
                            println!("actual out: {:#?}", state);
                        }
                    }

                    if let Some(filename) = lopts.write {
                        let mut path = TEST_CASE_DIR.clone();
                        path.push(filename);
                        std::fs::write(path, json_string).unwrap();
                    }


                    if !lopts.quiet {
                        for (case, result) in &report {
                            println!("{case}: {result}");
                        }
                    }

                    if report.values().any(|&result| result == false) {
                        1
                    } else {
                        0
                    }
                }

                TopLevelSubcommand::Bin(bopts) => todo!()
            };

            exit_code
        }

        pub static RUNNER_DIR: LazyLock<PathBuf> = LazyLock::new(|| {
            let mut path = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
            #[cfg(test)]
            {
                path.push("tests");
                path.push("test_data");
                path.push("mock_candidate_lib");
                path.push("runner");
            }
            #[cfg(fuzzing)]
            {
                path.pop();
            }
            path
        });


        /// The directory of the current test candidate.
        pub static CANDIDATE_DIR: LazyLock<PathBuf> = LazyLock::new(|| {
            let mut path = RUNNER_DIR.clone();
            path.pop();
            path
        });

        /// The directory of the current test candidate.
        pub static TEST_CASE_DIR: LazyLock<PathBuf> = LazyLock::new(|| {
            let mut path = CANDIDATE_DIR.clone();
            path.push("test_vectors");
            path
        });

        /// The name of the current test candidate.
        pub static CANDIDATE_NAME: LazyLock<String> = LazyLock::new(|| {
            let path = CANDIDATE_DIR.clone();
            let name = path.file_name().unwrap().to_os_string().into_string().unwrap();
            name
        });

        /// The name of the symbol for the current test candidate.
        pub static CANDIDATE_SYMBOL_NAME: LazyLock<String> = LazyLock::new(|| {
            CANDIDATE_NAME.strip_suffix("_lib").unwrap().to_string()
        });

        /// The shared library from which to load the symbol for the candidate.
        pub static LIBRARY: LazyLock<Library> = LazyLock::new(|| unsafe {
            use std::env;
            let mut path = match env::var("RUST_ARTIFACTS") {
                Ok(_) => {
                    let mut rust_path = CANDIDATE_DIR.clone();
                    rust_path.push("translated_rust");
                    rust_path.push("target");
                    rust_path.push("release");
                    rust_path
                },
                Err(_) => {
                    let mut c_path = CANDIDATE_DIR.clone();
                    c_path.push("build-ninja");
                    c_path
                }
            };
            path.push(get_lib_name(&*($lib)));
            Library::new(path).unwrap()
        });

        /// The symbol for the function that will be invoked as a test candidate.
        pub static SYMBOL: LazyLock<Symbol<$sig>> = LazyLock::new(|| unsafe {
            LIBRARY.get(($sym).as_bytes()).unwrap()
        });

        pub static DIFF_FLAG: std::sync::OnceLock<bool> = std::sync::OnceLock::new();

        /// This struct is created by the fields listed in the `state` argument
        /// to the `candidate` macro invocation.
        /// It represents the memory that is directly reachable from an
        /// invocation of the candidate function,
        /// meaning the input parameters
        /// (including any memory that is indirectly reachable from the input
        /// parameters, such as memory that is reachable via a pointer)
        /// and the function's return value
        /// (whose location in memory must be manually represented
        /// by the fields listed in the `state` argument).
        /// This function doesn't track file I/O or global variables.
        #[derive(Arbitrary, Clone, Debug, Deserialize, Serialize, PartialEq)]
        #[serde(crate = "self::serde", deny_unknown_fields)]
        pub struct State {
            $($field: $typ,)*
        }

        impl<'a> State {
            const SIZE: usize = std::mem::size_of::<Self>();

            /// Convenient for easily constructing an instance of `State`
            fn zeroed() -> Self {
                Self::from_bytes(&[])
            }

            /// This uses the `arbitrary` crate to allow you to construct
            /// an instance of `State` from any arbitrary bytes,
            /// which is to say that you don't need to be careful about
            /// what bytes you pass into this; it's not a transmute.
            fn from_bytes(bytes: &'a [u8]) -> Self {
                Self::arbitrary(&mut Unstructured::new(bytes)).unwrap()
            }

            fn from_json(s: &'a str) -> Self {
                from_str(s).unwrap()
            }

            /// This is the `run` function defined by the final argument
            /// to the `candidate` macro invocation.
            /// Its purpose is to invoke the test candidate with the
            /// appropriate parameters.
            /// Its `self` parameter represents an instance of `State`
            /// that has already been instantiated.
            /// The macro defines a global variable named `SYMBOL` which
            /// is a function pointer to the dynamically-linked test candidate.
            $run_fn

            fn to_json(&self) -> String {
                to_string_pretty(self).unwrap()
            }
        }

        /// This type is used for deserializing the expected output
        /// of a test case and comparing against a `State`.
        /// Its fields are all optional, which allows test cases
        /// to omit fields that they don't want to check.
        #[derive(Debug, Deserialize)]
        #[serde(crate = "self::serde", deny_unknown_fields)]
        pub struct ExpectedState {
            $($field: Option<$typ>,)*
        }

        impl PartialEq<ExpectedState> for State {
            fn eq(&self, other: &ExpectedState) -> bool {
                let mut retval = true;
                let diff = DIFF_FLAG.get().unwrap_or(&false).clone();
                // For every field that isn't `None`, compare against
                // the equivalent field in `State`.
                $(
                    if let Some(other_val) = &other.$field {
                        if self.$field != *other_val {
                            if diff {
                                println!("EXPECTED: {:#?}", other.$field);
                                println!("ACTUAL: {:#?}", self.$field);
                                retval = false;
                            }
                            else {
                                return false
                            }
                        }
                    }
                )*
                retval
            }
        }

        /// This type represents a single test case defined in a JSON file.
        #[derive(Debug, Deserialize)]
        #[serde(crate = "self::serde", deny_unknown_fields)]
        pub struct TestCase {
            /// For binary tests, the argv to `main`
            pub argv: Option<Vec<String>>,
            /// Data to pipe to the candidate over stdin
            pub stdin: Option<String>,
            /// The contents of stdout
            pub stdout: Option<Output>,
            /// The contents of stderr
            pub stderr: Option<Output>,
            /// For binary tests, the return code
            pub rc: Option<i32>,
            /// Whether or not the test case deliberately exhibits UB.
            /// When set, the string contains an explanation for the type of UB exhibited.
            pub has_ub: Option<String>,
            /// For library tests, the state before invoking the symbol
            pub lib_state_in: Option<State>,
            /// For library tests, the state after invoking the symbol
            pub lib_state_out: Option<ExpectedState>,
            /// Freeform string for test-specific comments, unused by test runner
            pub note: Option<String>,
        }

        #[derive(Debug, Deserialize)]
        #[serde(crate = "self::serde", deny_unknown_fields)]
        pub struct Output {
            pub pattern: String,
            /// When true, indicates that the `pattern` field should be compiled as a regex instead
            /// of used for a direct string comparison
            pub is_regex: Option<bool>,
        }

        impl<'a> TestCase {
            /// Loads from any JSON string
            fn from_json(json: &'a str) -> Self {
                from_str(json).unwrap()
            }

            /// Loads from any arbitrary path
            fn from_file(path: impl AsRef<Path>) -> Self {
                let json = std::fs::read_to_string(path).unwrap();
                Self::from_json(&json)
            }

            /// Loads from a file relative to the standard test_cases directory
            fn from_corpus(filename: &str) -> Self {
                let mut path = TEST_CASE_DIR.clone();
                path.push(filename);
                Self::from_file(path)
            }

            /// Loads all from the standard test_cases directory
            fn load_all() -> std::collections::HashMap<String, Self> {
                let mut tcs = std::collections::HashMap::new();

                for entry in std::fs::read_dir(&*TEST_CASE_DIR).unwrap() {
                    let path = entry.unwrap().path();

                    if let Some(ext) = path.extension() && ext.eq_ignore_ascii_case("json") {
                        let file_name = path.file_name().unwrap().to_str().unwrap().to_string();

                        let tc = Self::from_file(&path);

                        tcs.insert(file_name, tc);
                    }
                }

                tcs
            }

            /// This loads a copy of the lib state.
            /// Once loaded, it can be run via the `run` method on `State`.
            /// The copy here ensures that running the test does not
            /// unintentionally mutate this TestCase.
            fn lib_state(&self) -> State {
                self.lib_state_in.clone().unwrap()
            }

            fn equals_expected(&self, state: &State) -> bool {
                *state == *self.lib_state_out.as_ref().unwrap()
            }
        }

    };
}
