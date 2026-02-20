#!/usr/bin/env python3
"""
Test case generator for IMA ADPCM decoder library.
Generates comprehensive tests for ima_decode function.
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple


class IMATestGenerator:
    """Test generator for IMA ADPCM decoder."""
    
    def __init__(self, runner_dir="../runner", output_dir="test_cases", num_runs=5):
        self.runner_dir = Path(runner_dir)
        self.output_dir = Path(output_dir)
        self.num_runs = num_runs
        self.output_dir.mkdir(exist_ok=True)
        self.test_count = 0
    
    def run_test_safely(self, test_case: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], bool]:
        """Run test multiple times and detect UB."""
        temp_file = self.output_dir / "temp_test.json"
        results = []
        
        for run_num in range(self.num_runs):
            try:
                with open(temp_file, 'w') as f:
                    json.dump(test_case, f)
                
                result = subprocess.run(
                    ["cargo", "run", "--", "lib", "-c", str(temp_file.absolute())],
                    cwd=self.runner_dir,
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                
                results.append((result.stdout, result.stderr))
                
            except subprocess.TimeoutExpired:
                print(f"    Run {run_num + 1}/{self.num_runs}: Timeout (UB)")
                if temp_file.exists():
                    temp_file.unlink()
                return None, None, True
            except Exception as e:
                print(f"    Run {run_num + 1}/{self.num_runs}: Error - {e}")
                if temp_file.exists():
                    temp_file.unlink()
                return None, None, True
        
        if temp_file.exists():
            temp_file.unlink()
        
        # Check consistency
        stdout_set = set(r[0] for r in results)
        stderr_set = set(r[1] for r in results)
        
        has_ub = len(stdout_set) > 1 or len(stderr_set) > 1
        
        if has_ub:
            print(f"    UB: {len(stdout_set)} unique stdout, {len(stderr_set)} unique stderr")
        
        return results[0][0], results[0][1], has_ub
    
    def create_test(
        self,
        test_name: str,
        output_in: float,
        channel_count: int,
        block_preamble: int,
        block_data: List[int],
        decode_count: int,
        state_index_in: int,
        state_predict_in: int,
        output_out: float,
        state_index_out: int,
        state_predict_out: int,
        description: str = "",
        expect_buffer_overflow: bool = False
    ):
        """Create and run a single test case."""
        self.test_count += 1
        print(f"[{self.test_count:3d}] {test_name:<50} {description}")
        
        # Create test structure with ONLY the specified fields
        test_case = {
            "stdin": "",
            "lib_state_in": {
                "output": output_in,
                "channel_count": channel_count,
                "block": {
                    "preamble": block_preamble,
                    "data": block_data
                },
                "decode_count": decode_count,
                "state": {
                    "index": state_index_in,
                    "predict": state_predict_in
                }
            },
            "lib_state_out": {
                "output": output_out,
                "channel_count": channel_count,
                "block": {
                    "preamble": block_preamble,
                    "data": block_data
                },
                "decode_count": decode_count,
                "state": {
                    "index": state_index_out,
                    "predict": state_predict_out
                }
            }
        }
        
        # Mark buffer overflow tests
        if expect_buffer_overflow:
            test_case["has_ub"] = "buffer overflow expected"
        else:
            # Run the test to detect UB (only for non-overflow tests)
            stdout, stderr, has_ub = self.run_test_safely(test_case)
            
            if has_ub:
                test_case["has_ub"] = 1
        
        # Save test
        output_file = self.output_dir / f"{test_name}.json"
        with open(output_file, 'w') as f:
            json.dump(test_case, f, indent=2)
        
        return test_case
    
    def generate_all_tests(self):
        """Generate comprehensive test suite for IMA decoder."""
        print("=" * 80)
        print(" IMA ADPCM Decoder Test Generator")
        print("=" * 80)
        print()
        
        self.test_basic_decode()
        self.test_decode_count_variations()
        self.test_channel_count_variations()
        self.test_state_clamping()
        self.test_state_continuity()
        self.test_buffer_overflow()
        self.test_edge_cases()
        self.test_preamble_variations()
        
        print()
        print("=" * 80)
        print(f"✓ Generated {self.test_count} tests")
        print(f"  Location: {self.output_dir}")
        print("=" * 80)
    
    def test_basic_decode(self):
        """Test basic decoding functionality."""
        print("\n--- Basic Decode Tests ---")
        
        # Test 1: Decode 2 samples (1 byte, 2 nibbles)
        self.create_test(
            test_name="basic_001_decode_2_samples",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0000,  # index=0, predict=0
            block_data=[0x00] + [0] * 31,
            decode_count=2,
            state_index_in=0,
            state_predict_in=0,
            output_out=0.0,  # Will be calculated by actual run
            state_index_out=0,  # Will be updated
            state_predict_out=0,  # Will be updated
            description="Basic decode 2 samples"
        )
        
        # Test 2: Decode with non-zero initial output
        self.create_test(
            test_name="basic_002_nonzero_output",
            output_in=1.5,
            channel_count=1,
            block_preamble=0x0000,
            block_data=[0x11] + [0] * 31,
            decode_count=2,
            state_index_in=0,
            state_predict_in=0,
            output_out=1.5,
            state_index_out=0,
            state_predict_out=0,
            description="Non-zero initial output"
        )
        
        # Test 3: Decode with various nibble values
        self.create_test(
            test_name="basic_003_various_nibbles",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0000,
            block_data=[0xFF, 0xAA, 0x55, 0x0F] + [0] * 28,
            decode_count=8,
            state_index_in=0,
            state_predict_in=0,
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="Various nibble patterns"
        )
    
    def test_decode_count_variations(self):
        """Test different decode_count values."""
        print("\n--- Decode Count Variations ---")
        
        # Zero decode count
        self.create_test(
            test_name="decode_count_001_zero",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0000,
            block_data=[0xFF] * 32,
            decode_count=0,
            state_index_in=0,
            state_predict_in=0,
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="decode_count = 0"
        )
        
        # Odd decode counts (test the odd path)
        for count in [1, 3, 5, 7, 9, 15, 31, 63]:
            self.create_test(
                test_name=f"decode_count_002_odd_{count}",
                output_in=0.0,
                channel_count=1,
                block_preamble=0x0000,
                block_data=[0xAA] * 32,
                decode_count=count,
                state_index_in=0,
                state_predict_in=0,
                output_out=0.0,
                state_index_out=0,
                state_predict_out=0,
                description=f"decode_count = {count} (odd)"
            )
        
        # Even decode counts
        for count in [2, 4, 8, 16, 32, 64]:
            self.create_test(
                test_name=f"decode_count_003_even_{count}",
                output_in=0.0,
                channel_count=1,
                block_preamble=0x0000,
                block_data=[0x55] * 32,
                decode_count=count,
                state_index_in=0,
                state_predict_in=0,
                output_out=0.0,
                state_index_out=0,
                state_predict_out=0,
                description=f"decode_count = {count} (even)"
            )
        
        # Maximum valid decode_count (64 nibbles = 32 bytes)
        self.create_test(
            test_name="decode_count_004_max_valid",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0000,
            block_data=[0xFF] * 32,
            decode_count=64,
            state_index_in=0,
            state_predict_in=0,
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="decode_count = 64 (max valid)"
        )
    
    def test_channel_count_variations(self):
        """Test different channel_count values."""
        print("\n--- Channel Count Variations ---")
        
        for channels in [0, 1, 2, 4, 8, 16]:
            self.create_test(
                test_name=f"channel_count_001_{channels}",
                output_in=0.0,
                channel_count=channels,
                block_preamble=0x0000,
                block_data=[0xAA] * 32,
                decode_count=4,
                state_index_in=0,
                state_predict_in=0,
                output_out=0.0,
                state_index_out=0,
                state_predict_out=0,
                description=f"channel_count = {channels}"
            )
    
    def test_state_clamping(self):
        """Test index and predict clamping."""
        print("\n--- State Clamping Tests ---")
        
        # Test index clamping at boundaries
        test_indices = [
            (-100, "negative"),
            (-1, "minus_one"),
            (0, "zero"),
            (1, "one"),
            (44, "middle"),
            (87, "near_max"),
            (88, "max"),
            (89, "over_max"),
            (100, "way_over"),
        ]
        
        for index, name in test_indices:
            self.create_test(
                test_name=f"clamp_index_001_{name}",
                output_in=0.0,
                channel_count=1,
                block_preamble=0x0000,
                block_data=[0x00] * 32,
                decode_count=2,
                state_index_in=index,
                state_predict_in=0,
                output_out=0.0,
                state_index_out=0,
                state_predict_out=0,
                description=f"Initial index = {index}"
            )
        
        # Test predict clamping at boundaries
        test_predicts = [
            (-40000, "under_min"),
            (-32768, "min"),
            (-32767, "min_plus_one"),
            (0, "zero"),
            (32766, "max_minus_one"),
            (32767, "max"),
            (40000, "over_max"),
        ]
        
        for predict, name in test_predicts:
            self.create_test(
                test_name=f"clamp_predict_001_{name}",
                output_in=0.0,
                channel_count=1,
                block_preamble=0x0000,
                block_data=[0x00] * 32,
                decode_count=2,
                state_index_in=0,
                state_predict_in=predict,
                output_out=0.0,
                state_index_out=0,
                state_predict_out=0,
                description=f"Initial predict = {predict}"
            )
    
    def test_state_continuity(self):
        """Test state continuity check in the decoder."""
        print("\n--- State Continuity Tests ---")
        
        # Test when preamble matches state (continuity)
        self.create_test(
            test_name="continuity_001_match",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0A00,  # index=10, predict=0
            block_data=[0x00] * 32,
            decode_count=2,
            state_index_in=10,  # Matches preamble
            state_predict_in=0,   # Matches preamble
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="State matches preamble"
        )
        
        # Test when index matches but predict differs by small amount (<= 0x7f)
        self.create_test(
            test_name="continuity_002_small_diff",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0A00,  # index=10, predict=0
            block_data=[0x00] * 32,
            decode_count=2,
            state_index_in=10,
            state_predict_in=100,  # diff = 100 <= 0x7f
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="Small predict difference"
        )
        
        # Test when index matches but predict differs by large amount (> 0x7f)
        self.create_test(
            test_name="continuity_003_large_diff",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0A00,  # index=10, predict=0
            block_data=[0x00] * 32,
            decode_count=2,
            state_index_in=10,
            state_predict_in=200,  # diff = 200 > 0x7f
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="Large predict difference"
        )
        
        # Test when index doesn't match
        self.create_test(
            test_name="continuity_004_index_mismatch",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0A00,  # index=10
            block_data=[0x00] * 32,
            decode_count=2,
            state_index_in=5,  # Different index
            state_predict_in=0,
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="Index mismatch"
        )
    
    def test_buffer_overflow(self):
        """Test buffer overflow conditions."""
        print("\n--- Buffer Overflow Tests ---")
        
        # decode_count > 64 should overflow
        overflow_counts = [65, 66, 70, 80, 100, 128, 256, 1000]
        
        for count in overflow_counts:
            self.create_test(
                test_name=f"overflow_001_count_{count}",
                output_in=0.0,
                channel_count=1,
                block_preamble=0x0000,
                block_data=[0xFF] * 32,
                decode_count=count,
                state_index_in=0,
                state_predict_in=0,
                output_out=0.0,
                state_index_out=0,
                state_predict_out=0,
                description=f"Buffer overflow: decode_count={count}",
                expect_buffer_overflow=True
            )
        
        # Very large decode_count values
        for count in [10000, 100000, 0xFFFFFFFF]:
            self.create_test(
                test_name=f"overflow_002_large_{count}",
                output_in=0.0,
                channel_count=1,
                block_preamble=0x0000,
                block_data=[0x00] * 32,
                decode_count=count,
                state_index_in=0,
                state_predict_in=0,
                output_out=0.0,
                state_index_out=0,
                state_predict_out=0,
                description=f"Very large decode_count={count}",
                expect_buffer_overflow=True
            )
    
    def test_edge_cases(self):
        """Test various edge cases."""
        print("\n--- Edge Case Tests ---")
        
        # All nibbles set to 0xF (maximum)
        self.create_test(
            test_name="edge_001_all_max_nibbles",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0000,
            block_data=[0xFF] * 32,
            decode_count=64,
            state_index_in=0,
            state_predict_in=0,
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="All nibbles = 0xF"
        )
        
        # All nibbles set to 0x8 (sign bit)
        self.create_test(
            test_name="edge_002_all_sign_bit",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0000,
            block_data=[0x88] * 32,
            decode_count=64,
            state_index_in=0,
            state_predict_in=0,
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="All nibbles with sign bit"
        )
        
        # Alternating patterns
        self.create_test(
            test_name="edge_003_alternating_01",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0000,
            block_data=[0xAA] * 32,  # 10101010
            decode_count=64,
            state_index_in=0,
            state_predict_in=0,
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="Alternating bit pattern 0xAA"
        )
        
        self.create_test(
            test_name="edge_004_alternating_10",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x0000,
            block_data=[0x55] * 32,  # 01010101
            decode_count=64,
            state_index_in=0,
            state_predict_in=0,
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="Alternating bit pattern 0x55"
        )
        
        # Test with maximum index (88)
        self.create_test(
            test_name="edge_005_max_index_max_predict",
            output_in=0.0,
            channel_count=1,
            block_preamble=0x587F,  # index=88, predict=32767
            block_data=[0xFF] * 32,
            decode_count=8,
            state_index_in=88,
            state_predict_in=32767,
            output_out=0.0,
            state_index_out=0,
            state_predict_out=0,
            description="Max index and predict"
        )
    
    def test_preamble_variations(self):
        """Test various preamble values."""
        print("\n--- Preamble Variations ---")
        
        preambles = [
            (0x0000, "zero"),
            (0x0080, "index_0_predict_128"),
            (0x0100, "index_1_predict_0"),
            (0x0A00, "index_10_predict_0"),
            (0x5800, "index_88_predict_0"),
            (0xFF7F, "index_127_predict_neg128"),
            (0xFFFF, "all_bits_set"),
        ]
        
        for preamble, name in preambles:
            self.create_test(
                test_name=f"preamble_001_{name}",
                output_in=0.0,
                channel_count=1,
                block_preamble=preamble,
                block_data=[0x11] * 32,
                decode_count=8,
                state_index_in=0,
                state_predict_in=0,
                output_out=0.0,
                state_index_out=0,
                state_predict_out=0,
                description=f"Preamble = 0x{preamble:04X}"
            )


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate test cases for IMA ADPCM decoder"
    )
    parser.add_argument(
        "--runner-dir",
        default="../runner",
        help="Path to runner directory (default: ../runner)"
    )
    parser.add_argument(
        "--output-dir",
        default="test_cases",
        help="Output directory (default: test_cases)"
    )
    parser.add_argument(
        "--num-runs",
        type=int,
        default=5,
        help="Number of runs per test (default: 5)"
    )
    
    args = parser.parse_args()
    
    generator = IMATestGenerator(
        runner_dir=args.runner_dir,
        output_dir=args.output_dir,
        num_runs=args.num_runs
    )
    
    try:
        generator.generate_all_tests()
        print()
        print(f"✓ Test generation complete!")
        print(f"  {generator.test_count} tests saved to {generator.output_dir}/")
        
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
