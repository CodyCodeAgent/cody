---
name: testing
description: Software testing strategies, unit tests, integration tests, and test-driven development.
---

# Testing Skill

## When to use
- Writing unit tests or integration tests
- Setting up test infrastructure
- Improving code coverage
- Debugging test failures

## Best practices
- Follow the Arrange-Act-Assert pattern
- Use descriptive test names that explain the expected behavior
- Mock external dependencies (APIs, databases)
- Use fixtures for shared test setup
- Aim for isolated, independent tests
- Test edge cases and error paths

## Common patterns
```python
# pytest example
def test_add_returns_sum():
    result = add(2, 3)
    assert result == 5

# Using fixtures
@pytest.fixture
def sample_data():
    return {"name": "test", "value": 42}

def test_process_data(sample_data):
    result = process(sample_data)
    assert result is not None
```
