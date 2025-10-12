# 🧪 Comprehensive Testing Guide - Vechnost Bot

## 📋 **Overview**

This guide covers the comprehensive testing strategy implemented for the Vechnost bot, including unit tests, integration tests, performance tests, and error handling tests.

## 🏗️ **Test Architecture**

### **Test Structure**
```
tests/
├── conftest.py                          # Comprehensive test fixtures
├── test_integration_comprehensive.py     # End-to-end user flow tests
├── test_error_handling.py               # Error handling and recovery tests
├── test_performance_comprehensive.py     # Performance and load tests
├── test_*.py                            # Existing unit tests
└── pytest.ini                          # Pytest configuration
```

### **Test Categories**

#### 1. **Unit Tests** (`@pytest.mark.unit`)
- Individual component testing
- Mocked dependencies
- Fast execution (< 1 second per test)
- High isolation

#### 2. **Integration Tests** (`@pytest.mark.integration`)
- End-to-end user flows
- Real storage interactions
- Complete bot interactions
- Moderate execution time (1-5 seconds per test)

#### 3. **Performance Tests** (`@pytest.mark.performance`)
- Load testing
- Memory usage testing
- Response time testing
- Concurrent operation testing

#### 4. **Slow Tests** (`@pytest.mark.slow`)
- Long-running tests
- Load testing scenarios
- Benchmark tests
- Optional execution

## 🚀 **Running Tests**

### **Quick Start**
```bash
# Run all tests
python run_tests.py

# Run specific test types
python run_tests.py --type unit
python run_tests.py --type integration
python run_tests.py --type performance

# Run with coverage
python run_tests.py --coverage --html-report

# Run slow tests
python run_tests.py --slow

# Run in parallel
python run_tests.py --parallel 4
```

### **Direct Pytest Commands**
```bash
# Run all tests
pytest

# Run unit tests only
pytest -m unit

# Run integration tests only
pytest -m integration

# Run performance tests only
pytest -m performance

# Run with coverage
pytest --cov=vechnost_bot --cov-report=html

# Run specific test file
pytest tests/test_integration_comprehensive.py

# Run specific test
pytest tests/test_integration_comprehensive.py::TestCompleteUserFlows::test_complete_acquaintance_flow
```

## 🔧 **Test Fixtures**

### **Core Fixtures**

#### **Storage Fixtures**
```python
@pytest_asyncio.fixture
async def hybrid_storage_with_memory():
    """Hybrid storage that uses in-memory storage."""
    storage = HybridStorage()
    storage._redis_available = False
    storage._redis_checked = True
    return storage

@pytest_asyncio.fixture
async def mock_redis_storage():
    """Mock Redis storage."""
    storage = AsyncMock()
    # ... mock methods
    return storage
```

#### **Telegram API Fixtures**
```python
@pytest_asyncio.fixture
def mock_update(mock_message, mock_callback_query):
    """Mock Telegram update."""
    update = MagicMock(spec=Update)
    update.update_id = 1
    update.message = mock_message
    update.callback_query = mock_callback_query
    return update

@pytest_asyncio.fixture
def mock_context():
    """Mock Telegram context."""
    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    return context
```

#### **Session State Fixtures**
```python
@pytest_asyncio.fixture
def english_session():
    """Session with English language."""
    return SessionState(language=Language.ENGLISH)

@pytest_asyncio.fixture
def acquaintance_session():
    """Session with Acquaintance theme."""
    return SessionState(
        language=Language.ENGLISH,
        theme=Theme.ACQUAINTANCE,
        level=1,
        content_type=ContentType.QUESTIONS
    )
```

## 🎯 **Integration Tests**

### **Complete User Flows**

#### **Acquaintance Theme Flow**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_acquaintance_flow(
    self,
    mock_update,
    mock_context,
    hybrid_storage_with_memory
):
    """Test complete Acquaintance theme flow."""
    # Step 1: Start command
    # Step 2: Language selection
    # Step 3: Theme selection
    # Step 4: Level selection
    # Step 5: Question selection
```

#### **Sex Theme Flow with NSFW**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_sex_theme_flow(
    self,
    mock_update,
    mock_context,
    hybrid_storage_with_memory
):
    """Test complete Sex theme flow with NSFW confirmation."""
    # Step 1: Language selection
    # Step 2: Sex theme selection
    # Step 3: NSFW confirmation
    # Step 4: Toggle to tasks
```

#### **Reset Flow**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_reset_flow(
    self,
    mock_update,
    mock_context,
    hybrid_storage_with_memory
):
    """Test complete reset flow."""
    # Step 1: Create session with data
    # Step 2: Reset command
    # Step 3: Confirm reset
    # Step 4: Verify session reset
```

### **Navigation Flows**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_complete_navigation_flow(
    self,
    mock_update,
    mock_context,
    hybrid_storage_with_memory
):
    """Test complete navigation flow."""
    # Navigate through: question → next → prev → back to calendar → back to levels → back to themes
```

### **Multilingual Flows**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_multilingual_flow(
    self,
    mock_update,
    mock_context,
    hybrid_storage_with_memory
):
    """Test multilingual flow switching between languages."""
    # Switch between English → Russian → Czech
```

## ⚠️ **Error Handling Tests**

### **Error Recovery Scenarios**

#### **Invalid Callback Data Recovery**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_invalid_callback_data_recovery(
    self,
    mock_update,
    mock_context,
    hybrid_storage_with_memory
):
    """Test recovery from invalid callback data."""
    # Test with invalid callback data
    # Verify error message sent
    # Verify session intact
```

#### **Storage Failure Recovery**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_storage_failure_recovery(
    self,
    mock_update,
    mock_context,
    mock_redis_error
):
    """Test recovery from storage failures."""
    # Mock storage that fails
    # Test graceful handling
    # Verify error message sent
```

#### **Telegram API Failure Recovery**
```python
@pytest.mark.integration
@pytest.mark.asyncio
async def test_telegram_api_failure_recovery(
    self,
    mock_update,
    mock_context,
    hybrid_storage_with_memory,
    mock_telegram_error
):
    """Test recovery from Telegram API failures."""
    # Mock Telegram API failure
    # Test graceful handling
    # Verify fallback message sent
```

### **Custom Exception Hierarchy**

#### **Exception Types**
```python
# Base exception
class VechnostBotError(Exception):
    """Base exception for Vechnost bot errors."""
    pass

# Specific exceptions
class ValidationError(VechnostBotError):
    """Data validation error."""
    pass

class StorageError(VechnostBotError):
    """Storage operation error."""
    pass

class TelegramAPIError(VechnostBotError):
    """Telegram API error."""
    pass

class RateLimitError(VechnostBotError):
    """Rate limiting error."""
    pass

class SecurityError(VechnostBotError):
    """Security-related error."""
    pass

class ContentError(VechnostBotError):
    """Content-related error."""
    pass

class RenderingError(VechnostBotError):
    """Image rendering error."""
    pass

class LocalizationError(VechnostBotError):
    """Localization error."""
    pass

class NetworkError(VechnostBotError):
    """Network-related error."""
    pass

class FileOperationError(VechnostBotError):
    """File operation error."""
    pass
```

#### **Error Codes**
```python
class ErrorCodes:
    """Error code constants."""
    INVALID_THEME = "INVALID_THEME"
    INVALID_LEVEL = "INVALID_LEVEL"
    INVALID_LANGUAGE = "INVALID_LANGUAGE"
    INVALID_CALLBACK_DATA = "INVALID_CALLBACK_DATA"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    STORAGE_CONNECTION_FAILED = "STORAGE_CONNECTION_FAILED"
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_SAVE_FAILED = "SESSION_SAVE_FAILED"
    REDIS_CONNECTION_FAILED = "REDIS_CONNECTION_FAILED"
    TELEGRAM_API_ERROR = "TELEGRAM_API_ERROR"
    MESSAGE_SEND_FAILED = "MESSAGE_SEND_FAILED"
    CALLBACK_ANSWER_FAILED = "CALLBACK_ANSWER_FAILED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INVALID_INPUT = "INVALID_INPUT"
    CSRF_TOKEN_INVALID = "CSRF_TOKEN_INVALID"
    CONTENT_NOT_FOUND = "CONTENT_NOT_FOUND"
    THEME_NOT_AVAILABLE = "THEME_NOT_AVAILABLE"
    LEVEL_NOT_AVAILABLE = "LEVEL_NOT_AVAILABLE"
    IMAGE_RENDER_FAILED = "IMAGE_RENDER_FAILED"
    LOGO_GENERATION_FAILED = "LOGO_GENERATION_FAILED"
    TRANSLATION_NOT_FOUND = "TRANSLATION_NOT_FOUND"
    LANGUAGE_NOT_SUPPORTED = "LANGUAGE_NOT_SUPPORTED"
    NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
    CONNECTION_REFUSED = "CONNECTION_REFUSED"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_READ_FAILED = "FILE_READ_FAILED"
    FILE_WRITE_FAILED = "FILE_WRITE_FAILED"
```

## 🚀 **Performance Tests**

### **Storage Performance**
```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_session_save_performance(self, hybrid_storage_with_memory):
    """Test session save performance."""
    # Should complete within 100ms
    assert save_time < 0.1

@pytest.mark.performance
@pytest.mark.asyncio
async def test_concurrent_session_operations(self, hybrid_storage_with_memory):
    """Test concurrent session operations."""
    # Create 100 concurrent sessions
    # Should complete within 2 seconds
    assert total_time < 2.0
```

### **Callback Handler Performance**
```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_callback_processing_performance(
    self,
    mock_update,
    mock_context,
    hybrid_storage_with_memory
):
    """Test callback processing performance."""
    # Process multiple callbacks
    # Should complete within 1 second
    assert total_time < 1.0
```

### **Image Rendering Performance**
```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_question_card_rendering_performance(self, mock_image_operations):
    """Test question card rendering performance."""
    # Should complete within 500ms
    assert render_time < 0.5
```

### **Load Testing**
```python
@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.asyncio
async def test_high_load_scenario(self, hybrid_storage_with_memory):
    """Test high load scenario."""
    # Simulate 500 concurrent users
    # Should complete within 10 seconds
    assert total_time < 10.0
```

## 📊 **Coverage Goals**

### **Target Coverage**
- **Overall Coverage**: 80%+ (from current 54%)
- **Critical Modules**: 95%+ coverage
- **Integration Tests**: Complete user flow coverage
- **Error Scenarios**: 100% error path coverage

### **Coverage Reports**
```bash
# Generate coverage report
pytest --cov=vechnost_bot --cov-report=html

# View HTML report
open htmlcov/index.html

# Generate XML report
pytest --cov=vechnost_bot --cov-report=xml
```

## 🔍 **Test Debugging**

### **Verbose Output**
```bash
# Run with verbose output
pytest -v

# Run with extra verbose output
pytest -vv

# Show test durations
pytest --durations=10
```

### **Test Selection**
```bash
# Run specific test class
pytest tests/test_integration_comprehensive.py::TestCompleteUserFlows

# Run specific test method
pytest tests/test_integration_comprehensive.py::TestCompleteUserFlows::test_complete_acquaintance_flow

# Run tests matching pattern
pytest -k "test_complete_acquaintance"
```

### **Test Markers**
```bash
# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only performance tests
pytest -m performance

# Run only slow tests
pytest -m slow

# Run tests excluding slow ones
pytest -m "not slow"
```

## 🛠️ **CI/CD Integration**

### **GitHub Actions**
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -e .[dev]
      - name: Run tests
        run: |
          python run_tests.py --coverage
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

### **Local Development**
```bash
# Run tests before commit
python run_tests.py --coverage

# Run only fast tests during development
python run_tests.py --type unit

# Run full test suite before push
python run_tests.py --slow --coverage --html-report
```

## 📈 **Performance Monitoring**

### **Benchmarks**
```python
@pytest.mark.performance
@pytest.mark.slow
@pytest.mark.asyncio
async def test_benchmark_session_operations(self, hybrid_storage_with_memory):
    """Benchmark session operations."""
    # Performance requirements:
    # - Average save under 50ms
    # - 95th percentile save under 100ms
    # - Average get under 20ms
    # - 95th percentile get under 50ms
```

### **Memory Usage**
```python
@pytest.mark.performance
@pytest.mark.asyncio
async def test_memory_usage_under_load(self, hybrid_storage_with_memory):
    """Test memory usage under load."""
    # Memory increase should be reasonable (less than 50MB)
    assert memory_increase < 50 * 1024 * 1024
```

## 🎯 **Best Practices**

### **Test Writing**
1. **Use descriptive test names** that explain what is being tested
2. **Follow AAA pattern**: Arrange, Act, Assert
3. **Use appropriate fixtures** for test setup
4. **Mock external dependencies** in unit tests
5. **Test error scenarios** and edge cases
6. **Keep tests independent** and isolated

### **Test Organization**
1. **Group related tests** in classes
2. **Use appropriate markers** for test categorization
3. **Keep test files focused** on specific functionality
4. **Use conftest.py** for shared fixtures
5. **Follow naming conventions** for test files and methods

### **Performance Testing**
1. **Set realistic performance targets**
2. **Test under various load conditions**
3. **Monitor memory usage** and resource consumption
4. **Use statistical analysis** for performance metrics
5. **Include both average and percentile metrics**

## 🚀 **Getting Started**

### **Prerequisites**
```bash
# Install dependencies
pip install -e .[dev]

# Verify installation
python -c "import pytest; print('Pytest version:', pytest.__version__)"
```

### **First Test Run**
```bash
# Run all tests
python run_tests.py

# Run with coverage
python run_tests.py --coverage --html-report

# Run specific test type
python run_tests.py --type integration
```

### **Adding New Tests**
1. **Create test file** following naming convention
2. **Add appropriate markers** for test categorization
3. **Use existing fixtures** or create new ones
4. **Follow test structure** and best practices
5. **Update documentation** if needed

## 📚 **Additional Resources**

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest-Asyncio Documentation](https://pytest-asyncio.readthedocs.io/)
- [Python Testing Best Practices](https://docs.python.org/3/library/unittest.html)
- [Async Testing Patterns](https://docs.python.org/3/library/asyncio-testing.html)

---

**Happy Testing! 🎉**
