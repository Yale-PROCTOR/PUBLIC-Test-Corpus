// © 2026 Massachusetts Institute of Technology
// MIT License

use cando2::*;

harness! {
    state: {
        a: i32,
        b: i32,
        returns: i32
    },

    library: "mock_candidate_lib",

    symbol: "conduct_me",

    signature: extern "C" fn(i32, i32) -> i32,

    fn run(&mut self) {
        self.returns = (*SYMBOL)(self.a, self.b);
    }
}

#[test]
fn run_lib_test() {
    let tc = TestCase::from_corpus("1.json");
    let mut state = tc.lib_state();
    state.run();
    assert_eq!(state.returns, 3);
    assert_eq!(&state, tc.lib_state_out.as_ref().unwrap());
    assert!(tc.equals_expected(&state));
}

#[test]
fn conduct_one() {
    let args = &[
        "cando",
        "lib",
        "-c",
        "1.json",
    ];
    let code = conduct_with(args);
    assert_eq!(code, 0);
}

#[test]
fn conduct_failing_test() {
    let args = &[
        "cando",
        "lib",
        "-v",
        "-c",
        "3.json",
    ];
    let code = conduct_with(args);
    assert_eq!(code, 1);
}


#[test]
fn conduct_all() {
    let args = &[
        "cando",
        "lib"
    ];
    let code = conduct_with(args);
    assert_eq!(code, 1);
}

#[test]
fn conduct_zero() {
    let args = &[
        "cando",
        "lib",
        "-z"
    ];
    let code = conduct_with(args);
    assert_eq!(code, 0);
}
