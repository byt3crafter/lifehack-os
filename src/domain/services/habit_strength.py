"""Habit strength calculation service.

Strength is a continuous 0-100 score that replaces the brittle streak model.
It rises with completions and decays with misses, but never catastrophically.
"""


def calculate_strength_change(current_strength: float, completed: bool) -> float:
    """Calculate new strength after a completion or miss.

    - Completion: +2-5% (higher when strength is low, to encourage beginners)
    - Miss: -3-8% (higher when strength is high, because established habits
      decay slower early but you should know better by then)
    - Never goes below 0 or above 100
    - Missing one day does not crush progress
    """
    if completed:
        # Gain more when starting out, less when almost formed
        gain = max(2.0, 5.0 - (current_strength / 25.0))
        return min(100.0, current_strength + gain)
    else:
        # Lose less when just starting, more when you should know better
        loss = min(8.0, 3.0 + (current_strength / 33.0))
        return max(0.0, current_strength - loss)


def calculate_miss_penalty(current_strength: float, consecutive_misses: int) -> float:
    """Calculate new strength after a logged miss with accountability penalties.

    Applies the normal miss decay from calculate_strength_change() plus:
    - An additional flat -5% penalty for logging a miss
    - If consecutive_misses >= 3, strength is forced to 0 (habit reset)

    Args:
        current_strength: Current strength value (0-100).
        consecutive_misses: Number of consecutive missed days ending today.

    Returns:
        New strength value clamped to [0, 100].
    """
    if consecutive_misses >= 3:
        return 0.0

    # Normal decay
    base_loss = min(8.0, 3.0 + (current_strength / 33.0))
    new_strength = current_strength - base_loss

    # Additional flat accountability penalty
    new_strength -= 5.0

    return max(0.0, min(100.0, new_strength))


def get_strength_label(strength: float) -> str:
    """Return a human-readable label for a given strength value."""
    if strength >= 90:
        return "Automatic"
    if strength >= 70:
        return "Strong"
    if strength >= 50:
        return "Building"
    if strength >= 25:
        return "Forming"
    return "Starting"


def should_unlock_next_phase(strength: float, days_at_current: int) -> bool:
    """Phase unlocks when strength >= 80 for 7+ days."""
    return strength >= 80.0 and days_at_current >= 7
