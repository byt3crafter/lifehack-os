"""Configuration loader for rules and categories."""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any
import toml


@dataclass
class ScoringConfig:
    base_habit_points: int = 10
    streak_multiplier_threshold: int = 7
    streak_multiplier: float = 1.5
    weekly_consistency_bonus: int = 50
    sobriety_daily_bonus: int = 25


@dataclass
class LevelConfig:
    xp_per_level: int = 500
    level_names: List[str] = field(default_factory=lambda: [
        "Initiate", "Apprentice", "Practitioner", 
        "Adept", "Master", "Grandmaster", "Legend"
    ])


@dataclass
class PenaltyConfig:
    missed_habit: int = -5
    broken_sobriety: int = -100
    missed_checkin: int = -10
    enable_penalties: bool = True


@dataclass
class DeepWorkConfig:
    points_per_30min: int = 15
    max_daily_sessions: int = 4
    minimum_session_minutes: int = 25


@dataclass
class WalkConfig:
    base_points: int = 20
    km_bonus: int = 5
    mood_improvement_bonus: int = 10


@dataclass
class ReplacementConfig:
    urge_redirect_base: int = 30
    high_urge_bonus: int = 20


@dataclass
class CheckinConfig:
    completion_points: int = 15
    sobriety_bonus: int = 25
    future_work_bonus: int = 10


@dataclass
class CategoryInfo:
    name: str
    color: str
    icon: str


@dataclass
class Config:
    """Main configuration container."""
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    levels: LevelConfig = field(default_factory=LevelConfig)
    penalties: PenaltyConfig = field(default_factory=PenaltyConfig)
    deep_work: DeepWorkConfig = field(default_factory=DeepWorkConfig)
    walks: WalkConfig = field(default_factory=WalkConfig)
    replacements: ReplacementConfig = field(default_factory=ReplacementConfig)
    checkin: CheckinConfig = field(default_factory=CheckinConfig)
    categories: Dict[str, CategoryInfo] = field(default_factory=dict)
    replacement_categories: Dict[str, dict] = field(default_factory=dict)
    
    def get_level_name(self, level: int) -> str:
        """Get the name for a level number."""
        names = self.levels.level_names
        if level <= 0:
            return names[0]
        if level > len(names):
            return names[-1]
        return names[level - 1]


def load_config(config_dir: Path = None) -> Config:
    """Load configuration from TOML files."""
    if config_dir is None:
        config_dir = Path(__file__).parent.parent.parent.parent / "config"
    
    config = Config()
    
    # Load rules
    rules_path = config_dir / "rules.toml"
    if rules_path.exists():
        rules = toml.load(rules_path)
        
        if 'scoring' in rules:
            config.scoring = ScoringConfig(**rules['scoring'])
        if 'levels' in rules:
            config.levels = LevelConfig(**rules['levels'])
        if 'penalties' in rules:
            config.penalties = PenaltyConfig(**rules['penalties'])
        if 'deep_work' in rules:
            config.deep_work = DeepWorkConfig(**rules['deep_work'])
        if 'walks' in rules:
            config.walks = WalkConfig(**rules['walks'])
        if 'replacements' in rules:
            config.replacements = ReplacementConfig(**rules['replacements'])
        if 'checkin' in rules:
            config.checkin = CheckinConfig(**rules['checkin'])
    
    # Load categories
    cat_path = config_dir / "categories.toml"
    if cat_path.exists():
        cats = toml.load(cat_path)
        
        if 'categories' in cats:
            for key, value in cats['categories'].items():
                config.categories[key] = CategoryInfo(
                    name=value.get('name', key.title()),
                    color=value.get('color', '#6B7280'),
                    icon=value.get('icon', '📋')
                )
        
        if 'replacement_categories' in cats:
            config.replacement_categories = cats['replacement_categories']
    
    return config


# Global config instance
_config: Config = None

def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
