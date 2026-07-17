#!/usr/bin/env python3
"""
irrational_timers.py — Irrational Timer System
==============================================

Timers that wait for irrational durations based on random numbers
multiplied by mathematical constants. Perfect for avoiding synchronization,
throttling detection, or just embracing chaos.

Usage:
    from irrational_timers import IrrationalTimer
    
    timer = IrrationalTimer()
    timer.wait()  # waits random * π seconds
    
    # Or use specific constants
    timer.wait(constant='e')        # random * e
    timer.wait(constant='phi')      # random * φ
    timer.wait(constant='sqrt2')    # random * √2
    timer.wait(constant='sqrt3')    # random * √3
    timer.wait(constant='ln2')      # random * ln(2)
    timer.wait(constant='gamma')    # random * Euler-Mascheroni
    timer.wait(constant='zeta3')    # random * ζ(3)
    
    # Chaotic mode: random constant each time
    timer.wait_chaos()

    # With bounds
    timer.wait(constant='pi', min_sec=1, max_sec=60)
"""

import json
import math
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
CONSTANTS = {
    'pi': math.pi,                    # π ≈ 3.14159
    'e': math.e,                      # e ≈ 2.71828
    'phi': (1 + math.sqrt(5)) / 2,   # φ ≈ 1.61803
    'sqrt2': math.sqrt(2),            # √2 ≈ 1.41421
    'sqrt3': math.sqrt(3),            # √3 ≈ 1.73205
    'sqrt5': math.sqrt(5),            # √5 ≈ 2.23607
    'ln2': math.log(2),               # ln(2) ≈ 0.69315
    'ln10': math.log(10),             # ln(10) ≈ 2.30259
    'gamma': 0.5772156649015329,      # Euler-Mascheroni γ
    'zeta3': 1.202056903159594,       # Apéry's constant ζ(3)
    'catalan': 0.915965594177219,     # Catalan's constant G
    'sqrt_pi': math.sqrt(math.pi),    # √π ≈ 1.77245
    'e_pi': math.e * math.pi,         # eπ ≈ 8.53973
    'pi_e': math.pi ** math.e,        # π^e ≈ 22.4592
    'e_pi': math.e ** math.pi,        # e^π ≈ 23.1407
    'phi_pi': ((1 + math.sqrt(5)) / 2) * math.pi,  # φπ ≈ 5.0832
    'pi_phi': math.pi * ((1 + math.sqrt(5)) / 2),   # πφ ≈ 5.0832
}

# ─── Constant Groups ───
TRANSCENDENTAL = ['pi', 'e', 'pi_e', 'e_pi', 'e_pi', 'pi_phi']
ALGEBRAIC = ['phi', 'sqrt2', 'sqrt3', 'sqrt5', 'sqrt_pi']
LOGARITHMIC = ['ln2', 'ln10']
SPECIAL = ['gamma', 'zeta3', 'catalan']

ALL_CONSTANTS = list(CONSTANTS.keys())

@dataclass
class TimerState:
    """State of the irrational timer."""
    total_waits: int = 0
    total_seconds: float = 0.0
    constants_used: Dict[str, int] = field(default_factory=dict)
    wait_history: List[Dict[str, Any]] = field(default_factory=list)
    session_start: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def record_wait(self, constant: str, random_val: float, constant_val: float, wait_sec: float):
        self.total_waits += 1
        self.total_seconds += wait_sec
        self.constants_used[constant] = self.constants_used.get(constant, 0) + 1
        self.wait_history.append({
            'timestamp': datetime.now().isoformat(),
            'constant': constant,
            'random': random_val,
            'constant_val': constant_val,
            'wait_sec': wait_sec,
            'total_waits': self.total_waits,
            'total_seconds': self.total_seconds,
        })

class IrrationalTimer:
    """
    Timer that waits for irrational durations.
    
    Each wait = random() * constant, with optional bounds.
    """
    
    def __init__(
        self,
        default_constant: str = 'pi',
        min_wait: float = 0.1,
        max_wait: float = 300.0,
        seed: Optional[int] = None,
        state_file: Optional[str] = None,
    ):
        """
        Initialize the irrational timer.
        
        Args:
            default_constant: Default mathematical constant to use
            min_wait: Minimum wait time in seconds (safety floor)
            max_wait: Maximum wait time in seconds (safety ceiling)
            seed: Random seed for reproducibility (None = true random)
            state_file: Optional file to persist state
        """
        self.default_constant = default_constant
        self.min_wait = min_wait
        self.max_wait = max_wait
        self.state = TimerState()
        self.state_file = state_file
        
        if seed is not None:
            random.seed(seed)
        
        if state_file:
            self._load_state()
    
    def _load_state(self):
        """Load state from file."""
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
            self.state.total_waits = data.get('total_waits', 0)
            self.state.total_seconds = data.get('total_seconds', 0.0)
            self.state.constants_used = data.get('constants_used', {})
            self.state.wait_history = data.get('wait_history', [])
            self.state.session_start = data.get('session_start', self.state.session_start)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    
    def _save_state(self):
        """Save state to file."""
        if not self.state_file:
            return
        try:
            with open(self.state_file, 'w') as f:
                json.dump({
                    'total_waits': self.state.total_waits,
                    'total_seconds': self.state.total_seconds,
                    'constants_used': self.state.constants_used,
                    'wait_history': self.state.wait_history[-100:],  # Keep last 100
                    'session_start': self.state.session_start,
                }, f, indent=2)
        except Exception:
            pass
    
    def _calculate_wait(self, constant: str, min_sec: Optional[float] = None, max_sec: Optional[float] = None) -> tuple:
        """Calculate wait time: random * constant, with bounds."""
        const_val = CONSTANTS.get(constant.lower(), CONSTANTS['pi'])
        random_val = random.random()  # 0.0 to 1.0
        wait = random_val * const_val
        
        # Apply bounds
        floor = min_sec if min_sec is not None else self.min_wait
        ceiling = max_sec if max_sec is not None else self.max_wait
        wait = max(floor, min(ceiling, wait))
        
        return wait, random_val, const_val
    
    def wait(
        self,
        constant: Optional[str] = None,
        min_sec: Optional[float] = None,
        max_sec: Optional[float] = None,
        verbose: bool = True,
    ) -> float:
        """
        Wait for an irrational duration.
        
        Args:
            constant: Mathematical constant name (default: self.default_constant)
            min_sec: Override minimum wait
            max_sec: Override maximum wait
            verbose: Print wait info
            
        Returns:
            Actual seconds waited
        """
        const = (constant or self.default_constant).lower()
        if const not in CONSTANTS:
            raise ValueError(f"Unknown constant: {const}. Available: {ALL_CONSTANTS}")
        
        wait_sec, random_val, const_val = self._calculate_wait(const, min_sec, max_sec)
        
        if verbose:
            print(f"⏳ Irrational wait: {random_val:.6f} × {const} ({const_val:.6f}) = {wait_sec:.3f}s")
            if self.state.total_waits > 0:
                avg = self.state.total_seconds / self.state.total_waits
                print(f"   Total: {self.state.total_waits} waits, {self.state.total_seconds:.1f}s total, avg {avg:.2f}s")
        
        time.sleep(wait_sec)
        
        self.state.record_wait(const, random_val, const_val, wait_sec)
        self._save_state()
        
        return wait_sec
    
    def wait_chaos(
        self,
        min_sec: Optional[float] = None,
        max_sec: Optional[float] = None,
        verbose: bool = True,
    ) -> float:
        """Wait with a randomly selected constant each time."""
        const = random.choice(ALL_CONSTANTS)
        if verbose:
            print(f"🎲 Chaos mode: {const}")
        return self.wait(constant=const, min_sec=min_sec, max_sec=max_sec, verbose=verbose)
    
    def wait_sequence(
        self,
        constants: List[str],
        min_sec: Optional[float] = None,
        max_sec: Optional[float] = None,
        verbose: bool = True,
    ) -> List[float]:
        """Wait through a sequence of constants."""
        waits = []
        for const in constants:
            waits.append(self.wait(constant=const, min_sec=min_sec, max_sec=max_sec, verbose=verbose))
        return waits
    
    def wait_fibonacci(
        self,
        n: int = 5,
        base_constant: str = 'phi',
        min_sec: Optional[float] = None,
        max_sec: Optional[float] = None,
        verbose: bool = True,
    ) -> List[float]:
        """Wait using Fibonacci-scaled irrational durations."""
        # Generate Fibonacci sequence
        fib = [1, 1]
        for i in range(2, n):
            fib.append(fib[-1] + fib[-2])
        
        waits = []
        for i, f in enumerate(fib):
            # Scale by Fibonacci number
            wait = self.wait(
                constant=base_constant,
                min_sec=(min_sec or self.min_wait) * f if min_sec else None,
                max_sec=(max_sec or self.max_wait) * f if max_sec else None,
                verbose=verbose,
            )
            waits.append(wait)
            if verbose:
                print(f"   Fibonacci {i+1}/{n}: F({i+1})={f} × wait")
        return waits
    
    def wait_primes(
        self,
        n: int = 5,
        constant: str = 'pi',
        min_sec: Optional[float] = None,
        max_sec: Optional[float] = None,
        verbose: bool = True,
    ) -> List[float]:
        """Wait using prime-number scaled durations."""
        def gen_primes(limit):
            primes = []
            candidate = 2
            while len(primes) < limit:
                if all(candidate % p != 0 for p in primes):
                    primes.append(candidate)
                candidate += 1
            return primes
        
        primes = gen_primes(n)
        waits = []
        for i, p in enumerate(primes):
            wait = self.wait(
                constant=constant,
                min_sec=(min_sec or self.min_wait) * p if min_sec else None,
                max_sec=(max_sec or self.max_wait) * p if max_sec else None,
                verbose=verbose,
            )
            waits.append(wait)
            if verbose:
                print(f"   Prime {i+1}/{n}: p={p} × wait")
        return waits
    
    def get_stats(self) -> Dict[str, Any]:
        """Get timer statistics."""
        return {
            'total_waits': self.state.total_waits,
            'total_seconds': self.state.total_seconds,
            'average_wait': self.state.total_seconds / max(self.state.total_waits, 1),
            'constants_used': self.state.constants_used,
            'session_start': self.state.session_start,
            'recent_waits': self.state.wait_history[-10:],
        }
    
    def print_stats(self):
        """Print formatted statistics."""
        stats = self.get_stats()
        print(f"\n📊 Irrational Timer Statistics")
        print(f"   Total waits: {stats['total_waits']}")
        print(f"   Total time: {stats['total_seconds']:.2f}s")
        print(f"   Average wait: {stats['average_wait']:.2f}s")
        print(f"   Constants used: {stats['constants_used']}")
        print(f"   Session: {stats['session_start']}")


# ─── Slash Command Interface ───
def slash_irrational(args: str) -> str:
    """Parse: /irrational [constant] [--min N] [--max N] [--chaos] [--fib N] [--primes N] [--stats]"""
    import shlex
    parts = shlex.split(args)
    
    if not parts:
        return "Usage: /irrational [constant] [--min N] [--max N] [--chaos] [--fib N] [--primes N] [--stats]"
    
    timer = IrrationalTimer(state_file="/tmp/irrational_timer_state.json")
    
    if parts[0] == 'stats':
        timer.print_stats()
        return ""
    
    constant = parts[0] if parts[0] in CONSTANTS else 'pi'
    min_sec = None
    max_sec = None
    chaos = False
    fib_n = 0
    primes_n = 0
    
    i = 1
    while i < len(parts):
        if parts[i] == '--min' and i + 1 < len(parts):
            min_sec = float(parts[i + 1]); i += 2
        elif parts[i] == '--max' and i + 1 < len(parts):
            max_sec = float(parts[i + 1]); i += 2
        elif parts[i] == '--chaos':
            chaos = True; i += 1
        elif parts[i] == '--fib' and i + 1 < len(parts):
            fib_n = int(parts[i + 1]); i += 2
        elif parts[i] == '--primes' and i + 1 < len(parts):
            primes_n = int(parts[i + 1]); i += 2
        else:
            i += 1
    
    if chaos:
        wait = timer.wait_chaos(min_sec=min_sec, max_sec=max_sec)
        return f"Chaos wait: {wait:.3f}s"
    elif fib_n > 0:
        waits = timer.wait_fibonacci(fib_n, min_sec=min_sec, max_sec=max_sec)
        return f"Fibonacci waits: {[f'{w:.3f}' for w in waits]}"
    elif primes_n > 0:
        waits = timer.wait_primes(primes_n, min_sec=min_sec, max_sec=max_sec)
        return f"Prime waits: {[f'{w:.3f}' for w in waits]}"
    else:
        wait = timer.wait(constant=constant, min_sec=min_sec, max_sec=max_sec)
        return f"Waited {wait:.3f}s ({constant})"


# ─── Main ───


# ─── AI Improvement: Cycle 1 ───
# Applied: 2026-07-15T23:09:35.287947+00:00
# This file is being continuously improved by the Intelligent Growth Engine


# ─── AI Improvement: Cycle 15 ───
# Applied: 2026-07-15T23:43:29.768352+00:00
# This file is being continuously improved by the Intelligent Growth Engine
if __name__ == "__main__":
    import json
    import sys
    
    if len(sys.argv) > 1:
        print(slash_irrational(" ".join(sys.argv[1:])))
    else:
        # Demo
        print("🌀 Irrational Timer Demo")
        print("=" * 40)
        
        timer = IrrationalTimer(default_constant='phi', min_wait=0.5, max_wait=5.0)
        
        print("\n1. Single wait (default φ):")
        timer.wait()
        
        print("\n2. Wait with π:")
        timer.wait(constant='pi', min_sec=1, max_sec=3)
        
        print("\n3. Chaos mode (random constant):")
        timer.wait_chaos(min_sec=0.5, max_sec=2)
        
        print("\n4. Fibonacci sequence (3 steps):")
        timer.wait_fibonacci(3, base_constant='pi', min_sec=0.5, max_sec=2)
        
        print("\n5. Prime sequence (3 steps):")
        timer.wait_primes(3, constant='e', min_sec=0.5, max_sec=2)
        
        print("\n6. Statistics:")
        timer.print_stats()
        
        print("\n✅ Demo complete")