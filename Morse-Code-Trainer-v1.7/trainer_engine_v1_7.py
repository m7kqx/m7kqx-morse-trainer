"""
trainer_engine_v1_7.py - Morse Trainer v1.7
Manages multiple profiles, dynamic challenge weighting, progressive pool limits, 
user response metrics, Koch progression, and session-based state advancement.
"""

import json
import glob
import random
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from word_banks import get_bank

KOCH_SEQUENCE: List[str] = [
    "K", "M", "R", "S", "U", "A", "P", "T", "L", "O",
    "W", "I", ".", "N", "J", "E", "F", "0", "Y", "V",
    ",", "G", "5", "/", "Q", "9", "Z", "H", "3", "8",
    "B", "?", "4", "2", "7", "C", "1", "D", "6", "X",
]

# v1.7: Profiles now save to a visible 'profiles' folder in the current working directory
STORAGE_DIR = Path("profiles")


@dataclass
class TokenMetric:
    attempts: int = 0
    correct: int = 0
    streak: int = 0

    @property
    def accuracy(self) -> float:
        return (self.correct / self.attempts * 100.0) if self.attempts > 0 else 0.0

    @property
    def is_proficient(self) -> bool:
        return self.attempts >= 5 and self.accuracy >= 70.0


@dataclass
class TrainerState:
    koch_level: int = 2
    char_wpm: int = 20
    effective_wpm: int = 12
    training_mode: str = "KOCH"
    session_length: int = 10  
    pool_limits: Dict[str, int] = field(
        default_factory=lambda: {
            "WORDS_2": 4,
            "WORDS_3": 4,
            "WORDS_4": 4,
            "NAMES": 4,
            "QSO": 4,
        }
    )
    metrics: Dict[str, TokenMetric] = field(default_factory=dict)


class ProfileManager:
    def __init__(self, profile_name: str = "default"):
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        self.profile_name = profile_name
        self.filepath = STORAGE_DIR / f"{self.profile_name}_v1_7.json"
        self.state = self.load_profile()
        self.session_metrics: Dict[str, TokenMetric] = defaultdict(TokenMetric)

    @staticmethod
    def list_profiles() -> List[str]:
        STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        files = glob.glob(str(STORAGE_DIR / "*_v1_7.json"))
        return [Path(f).stem.replace("_v1_7", "") for f in files]

    @staticmethod
    def delete_profile(profile_name: str) -> None:
        path = STORAGE_DIR / f"{profile_name}_v1_7.json"
        if path.exists():
            path.unlink()

    def load_profile(self) -> TrainerState:
        if not self.filepath.exists():
            return TrainerState()
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                metrics = {}
                for k, v in data.get("metrics", {}).items():
                    # Safely drop legacy latency metrics if migrating from v1.6
                    v.pop("total_latency_ms", None)
                    v.pop("best_latency_ms", None)
                    metrics[k] = TokenMetric(**v)
                
                default_limits = {"WORDS_2": 4, "WORDS_3": 4, "WORDS_4": 4, "NAMES": 4, "QSO": 4}
                default_limits.update(data.get("pool_limits", {}))
                return TrainerState(
                    koch_level=data.get("koch_level", 2),
                    char_wpm=data.get("char_wpm", 20),
                    effective_wpm=data.get("effective_wpm", 12),
                    training_mode=data.get("training_mode", "KOCH"),
                    session_length=data.get("session_length", 10),
                    pool_limits=default_limits,
                    metrics=metrics,
                )
        except Exception:
            return TrainerState()

    def save_profile(self) -> None:
        raw_metrics = {k: asdict(v) for k, v in self.state.metrics.items()}
        payload = {
            "koch_level": self.state.koch_level,
            "char_wpm": self.state.char_wpm,
            "effective_wpm": self.state.effective_wpm,
            "training_mode": self.state.training_mode,
            "session_length": self.state.session_length,
            "pool_limits": self.state.pool_limits,
            "metrics": raw_metrics,
        }
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def reset_profile(self) -> None:
        self.state = TrainerState()
        self.save_profile()

    def start_session(self) -> None:
        self.session_metrics.clear()

    def get_weak_pool(self, limit: int = 10) -> List[str]:
        struggles = [k for k, v in self.state.metrics.items() if v.attempts > 0]
        struggles.sort(key=lambda x: self.state.metrics[x].accuracy)
        return struggles[:limit] if struggles else ["K", "M"]

    def get_active_pool(self, mode: str) -> List[str]:
        if mode == "WEAK" or mode == "HEAD_COPY":
            return self.get_weak_pool() if mode == "WEAK" else KOCH_SEQUENCE[:self.state.koch_level]
        if mode == "KOCH":
            lvl = max(2, min(self.state.koch_level, len(KOCH_SEQUENCE)))
            return KOCH_SEQUENCE[:lvl]

        full_bank = list(get_bank(mode))
        limit = self.state.pool_limits.get(mode, 4)
        return full_bank[: min(limit, len(full_bank))]

    def get_next_challenge(self, mode: str) -> str:
        """Calculates dynamic priority weights to enforce practice on weak/new characters."""
        active_pool = self.get_active_pool(mode)
        weights = []

        for item in active_pool:
            global_metric = self.state.metrics.get(item, TokenMetric())
            session_metric = self.session_metrics.get(item, TokenMetric())

            # 1. Base Weight ensures highly accurate characters never hit 0% probability
            weight = 1.0

            # 2. Session Deprivation Weighting
            if session_metric.attempts == 0:
                weight += 20.0
            elif session_metric.attempts < 5:
                weight += 10.0

            # 3. New Letter Priority Weighting
            if global_metric.attempts < 10:
                weight += 30.0

            # 4. Inaccuracy Weighting
            acc = global_metric.accuracy if global_metric.attempts > 0 else 0.0
            weight += (100.0 - acc) * 0.5 

            weights.append(weight)

        return random.choices(active_pool, weights=weights, k=1)[0]

    def record_response(self, plain_text: str, is_correct: bool) -> None:
        # Update Global Profile Metrics
        if plain_text not in self.state.metrics:
            self.state.metrics[plain_text] = TokenMetric()

        m = self.state.metrics[plain_text]
        m.attempts += 1
        if is_correct:
            m.correct += 1
            m.streak += 1
        else:
            m.streak = 0
            
        # Update Local Session Metrics
        sm = self.session_metrics[plain_text]
        sm.attempts += 1
        if is_correct:
            sm.correct += 1

        self.save_profile()

    def should_show_dotrep(self, plain_text: str) -> bool:
        if plain_text not in self.state.metrics:
            return True
        return not self.state.metrics[plain_text].is_proficient

    def evaluate_advancement(self, mode: str) -> Optional[str]:
        if mode in ("KOCH", "HEAD_COPY"):
            # Check if we are already at max level
            if self.state.koch_level >= len(KOCH_SEQUENCE):
                return None
            
            # Target the most recently introduced letter
            current_target = KOCH_SEQUENCE[self.state.koch_level - 1]
            metric = self.state.metrics.get(current_target)
            
            # Advance as soon as the latest letter is learned!
            if metric and metric.attempts >= 5 and metric.accuracy >= 70.0:
                self.state.koch_level += 1
                self.save_profile()
                new_letter = KOCH_SEQUENCE[self.state.koch_level - 1]
                return f"Koch Level {self.state.koch_level} (+ '{new_letter}')"
            return None

        else:
            full_bank = get_bank(mode)
            current_limit = self.state.pool_limits.get(mode, 4)
            active_pool = self.get_active_pool(mode)
            
            for item in active_pool:
                metric = self.state.metrics.get(item)
                if not metric or metric.attempts < 5 or metric.accuracy < 70.0:
                    return None

            if current_limit < len(full_bank):
                new_limit = min(current_limit + 2, len(full_bank))
                self.state.pool_limits[mode] = new_limit
                self.save_profile()
                newly_added = ", ".join(full_bank[current_limit:new_limit])
                return f"Active Pool expanded to {new_limit} items (+ {newly_added})"

        return None
