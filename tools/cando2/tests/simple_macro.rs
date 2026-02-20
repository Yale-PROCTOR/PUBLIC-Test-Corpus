// © 2026 Massachusetts Institute of Technology
// MIT License

use cando2::*;

harness! {
    state: {
        input: i32,
        returns: i32
    },

    signature: extern "C" fn(i32) -> i32,

    fn run(&mut self) {
        self.returns = (*SYMBOL)(self.input);
    }
}

#[test]
fn statics() {
    assert_eq!("mock_candidate_lib", &*CANDIDATE_NAME);
    let _ = &*LIBRARY;
    let _ = &*SYMBOL;
}

#[test]
fn run() {
    let mut state = State::zeroed();
    assert_eq!(state.returns, 0);
    state.run();
    assert_eq!(state.returns, 3);
}
