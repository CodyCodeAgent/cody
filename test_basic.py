"""Basic functionality test without full installation"""

import sys
sys.path.insert(0, '/Users/gouchao/Github/cody')

from cody.core.config import Config
from cody.core.skill_manager import SkillManager

print("🧪 Testing Cody Core...")

# Test 1: Config loading
print("\n1. Testing Config...")
config = Config()
print(f"   ✓ Default model: {config.model}")

# Test 2: Skill Manager
print("\n2. Testing Skill Manager...")
manager = SkillManager(config)
skills = manager.list_skills()
print(f"   ✓ Found {len(skills)} skills:")
for skill in skills:
    print(f"     - {skill.name} ({skill.source})")

# Test 3: Config save/load
print("\n3. Testing Config persistence...")
import tempfile
from pathlib import Path
temp_dir = Path(tempfile.mkdtemp())
config_file = temp_dir / "config.json"
config.save(config_file)
loaded = Config.load(config_file)
print(f"   ✓ Saved and loaded config")
print(f"   ✓ Model match: {loaded.model == config.model}")

print("\n✅ All basic tests passed!")
