This repo contains a fork of the Rust compiler with a small patch applied to make the
compiler emit diagnostics whenever it encounters an "unsafe" operation, defined
as any operation that requires an unsafe context to call.

In other words, this tool flags any operation which, if not inside of an
`unsafe` block, would cause a compiler error.
The set of operations that this flags is given by the following enum:

```rust
enum UnsafeOpKind {
    CallToUnsafeFunction(Option<DefId>),
    UseOfInlineAssembly,                                                                        
    InitializingTypeWith,
    InitializingTypeWithUnsafeField,
    UseOfMutableStatic,                                                                         
    UseOfExternStatic,
    UseOfUnsafeField,                                                                           
    DerefOfRawPointer,
    AccessToUnionField,
    MutationOfLayoutConstrainedField,
    BorrowOfLayoutConstrainedField,
    CallToFunctionWith {
        function: DefId,
        /// Target features enabled in callee's `#[target_feature]` but missing in
        /// caller's `#[target_feature]`.
        missing: Vec<Symbol>,
        /// Target features in `missing` that are enabled at compile time
        /// (e.g., with `-C target-feature`).
        build_enabled: Vec<Symbol>,
    },                                                                                          
    UnsafeBinderCast,
}
```

Notably, this does *not* flag any of the following:

  * unsafe attributes, `#[unsafe(foo)]`
  * unsafe traits, `unsafe trait Foo {}`
  * unsafe impls, `unsafe impl Foo for Bar {}`

# How to build and install

First, clone the Rust repo at https://github.com/rust-lang/rust/ .

You will likely want to check out a known-good commit upon which
to apply the patch.
The patch is known to work with the following commit:

```bash
git checkout 7d8ebe3128fc87f3da1ad64240e63ccf07b8f0bd
```

Then apply the unsafe_ops_checker.patch as follows:

```bash
git apply --check unsafe_ops_checker.patch
```

Then, from inside the Rust repo, run the following command to configure
the rustc bootstrapper.
When it asks what you want to contribute to, answer with the option that
corresponds to "compiler".

```bash
./x setup
```

Then, build the compiler:

```bash
./x build --stage 1 library
```

This will take a while.

Once the compiler is built, you will want to link it to a rustup toolchain:

```bash
rustup toolchain link TractorUnsafeOpsFork build/host/stage1/
```

Now the tool can be used with any rustup-managed binary (Cargo, rustc, etc)
by passing `+TractorUnsafeOpsFork` as the first argument,
e.g. `cargo +TractorUnsafeOpsFork check`.

# How to use

This tool only prints diagnostics when the TRACTOR_UNSAFE_OPS environment
variable is set.

To analyze a codebase, we recommend the following command from within a
Cargo project:

```bash
RUSTFLAGS='-C codegen-units=1' TRACTOR_UNSAFE_OPS=1 cargo clean && cargo +TractorUnsafeOpsFork -vv check > unsafeops.txt && grep -Po "TRACTOR_UNSAFE_OPS \K({.*})" unsafeops.txt
```

Notes:

  * We restrict rustc to a single codegen unit so as to eliminate the
possibility of double-counting unsafe operations.
  * We perform a `cargo clean` first to force the compiler to actually run.
  * We use `-vv` to print super-verbose output so that Cargo will not swallow
rustc's output.
  * We grep for (and discard) the prefix TRACTOR_UNSAFE_OPS, leaving only the
diagnostic line for each unsafe operation.
  * When invoking this tool via Cargo, it will count unsafe operations in
*every* crate that is encountered, including third-party crates. You can use
the "span" field to attempt to filter out third-party dependencies. It will
also probably(?) count unsafe operations performed by stdlib macros that
happen to use unsafe code internally, which should likewise be filtered.

The above command will result in output like this:

```
{"kind": "CallToUnsafeFunction(Some(DefId(2:2453 ~ core[dc26]::mem::uninitialized)))", "span": "src/lib.rs:5:23: 5:48 (#0)"}
{"kind": "DerefOfRawPointer", "span": "src/lib.rs:6:21: 6:38 (#0)"}
```

This represents a program with two unsafe operations.
Each operation has a "kind" and a "span".
The kind maps to variants of the enum given above.
The span tells you where and in what file the operation occurs.
