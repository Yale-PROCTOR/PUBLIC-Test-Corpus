// © 2026 Massachusetts Institute of Technology
// MIT License

use cando2::*;

harness! {
    state: {
        a: i32,
        b: i32,
        returns: i32
    },

    signature: extern "C" fn(),

    fn run(&mut self) {}
}

#[test]
fn load_from_json() {
    let json = r#"
    {
        "lib_state_in": {
            "a": 1,
            "b": 2,
            "returns": 0
        },
        "lib_state_out": {
            "a": 1,
            "b": 2,
            "returns": 0
        }
    }
    "#;
    let tc = TestCase::from_json(json);
    assert_eq!(tc.lib_state_in.unwrap(), tc.lib_state_out.unwrap());
}

#[test]
fn eq_with_skipped_field() {
    let json = r#"
    {
        "lib_state_in": {
            "a": 1,
            "b": 2,
            "returns": 0
        },
        "lib_state_out": {
            "a": 1,
            "b": 2
        }
    }
    "#;
    let tc = TestCase::from_json(json);
    assert_eq!(tc.lib_state_in.unwrap(), tc.lib_state_out.unwrap());
}

#[test]
fn load_from_file() {
    let path = "tests/test_data/mock_candidate_lib/test_vectors/1.json";
    let tc = TestCase::from_file(path);
    assert_eq!(tc.lib_state_in.unwrap().a, 1);
    assert_eq!(tc.lib_state_out.unwrap().returns.unwrap(), 3);
}

#[test]
fn load_from_corpus() {
    let tc = TestCase::from_corpus("1.json");
    assert_eq!(tc.lib_state_in.unwrap().a, 1);
    assert_eq!(tc.lib_state_out.unwrap().returns.unwrap(), 3);
}

#[test]
fn load_entire_corpus() {
    let tcs = TestCase::load_all();
    let tc1 = &tcs["1.json"];
    assert_eq!(tc1.lib_state_in.as_ref().unwrap().a, 1);
    assert_eq!(tc1.lib_state_out.as_ref().unwrap().returns.unwrap(), 3);
    let tc2 = &tcs["2.json"];
    assert_eq!(tc2.lib_state_in.as_ref().unwrap().a, 4);
    assert_eq!(tc2.lib_state_out.as_ref().unwrap().returns.unwrap(), 9);
}

#[test]
fn load_lib_state() {
    let tc = TestCase::from_corpus("1.json");
    let state = tc.lib_state();
    assert_eq!(state.a, 1);
    assert_eq!(state.b, 2);
    assert_eq!(state.returns, 0);
}
