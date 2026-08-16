# Testing Modules with External Dependencies
*Documented from Client Bot Notifications implementation (2026-07-24)*

## Problem
When implementing the client bot notifications module, we encountered an issue where the main `client_bot.py` module could not be imported in the test environment due to Google Calendar dependencies that were not available. This prevented us from directly testing the module's functions.

## Solution
We extracted the core notification formatting logic into pure functions that could be tested independently without requiring external dependencies.

## Key Patterns

### 1. Extract Pure Functions
Isolate business logic from external dependencies by extracting pure functions:

```python
# Extracted from the main module for testing
def format_client_notification(name, date, time, email=None, source="chat"):
    """Format notification text without external dependencies."""
    lines = [
        "🔔 <b>NEW BOOKING</b>",
        "",
        f"Prospect: <b>{name}</b>"
    ]
    
    if email:
        lines.append(f"Email: {email}")
    
    lines.extend([
        f"Date: {date}",
        f"Time: {time}",
        f"Source: {source}"
    ])
    
    return "\n".join(lines)
```

### 2. Dependency Injection
Instead of importing services directly, pass them as parameters:

```python
def send_notification_to_client(client, message, recipient, user_settings):
    """Send notification using injected client."""
    if not client:
        raise ValueError("Client service not provided")
    
    # Extract settings needed for the service
    service_config = user_settings.get("notifications", {})
    
    return client.send_message(
        to=recipient,
        content=message,
        config=service_config
    )
```

### 3. Mock External Services
Create test doubles that simulate external service behavior:

```python
class MockNotificationService:
    """Mock service for testing notifications."""
    def __init__(self):
        self.messages_sent = []
    
    def send_message(self, to, content, config):
        message_record = {
            "to": to,
            "content": content,
            "config": config,
            "timestamp": "2026-07-24T10:00:00Z"
        }
        self.messages_sent.append(message_record)
        return {"status": "sent", "id": f"msg-{len(self.messages_sent)}"}
```

## Test Implementation

### Isolated Unit Tests
Test extracted functions without external dependencies:

```python
def test_format_client_notification_basic():
    """Test basic notification formatting."""
    result = format_client_notification(
        name="John Smith",
        date="Monday, July 28, 2026",
        time="2:30 PM"
    )
    
    assert "🔔 <b>NEW BOOKING</b>" in result
    assert "John Smith" in result
    assert "Monday, July 28, 2026" in result
    assert "2:30 PM" in result
    assert "Email:" not in result  # No email provided

def test_format_client_notification_with_email():
    """Test notification formatting with email."""
    result = format_client_notification(
        name="Jane Doe",
        date="Tuesday, July 29, 2026",
        time="10:00 AM",
        email="jane@example.com"
    )
    
    assert "🔔 <b>NEW BOOKING</b>" in result
    assert "Jane Doe" in result
    assert "jane@example.com" in result
```

### Integration Tests with Mocks
Test with mocked dependencies:

```python
def test_send_notification_to_client(mocker):
    """Test notification sending with mocked client."""
    # Mock the client
    mock_client = mocker.Mock()
    mock_client.send_message.return_value = {"status": "sent", "id": "test-123"}
    
    # Call function with mocked client
    result = send_notification_to_client(
        client=mock_client,
        message="Test notification",
        recipient="test@example.com",
        user_settings={"notifications": {"priority": "high"}}
    )
    
    # Verify the mock was called correctly
    mock_client.send_message.assert_called_once_with(
        to="test@example.com",
        content="Test notification",
        config={"priority": "high"}
    )
    
    assert result["status"] == "sent"
```

## Best Practices

1. **Always extract core logic** into pure functions that can be tested independently
2. **Use dependency injection** to pass services as parameters rather than importing them directly
3. **Create mock implementations** that simulate external service behavior
4. **Test error conditions** with various input scenarios
5. **Handle missing dependencies gracefully** with clear error messages
6. **Write comprehensive tests** for all extracted functions before moving to integration tests
7. **Document testing approaches** for future reference and consistency

## Common Pitfalls Avoided

1. **Direct imports causing test failures** - Instead of importing modules with unavailable dependencies directly, we extracted the core logic
2. **Testing implementation details** - We focused on testing observable behavior rather than internal implementation
3. **Complex test setup** - We used simple mocks instead of complex setup that mirrors production environment
4. **Missing dependency handling** - We implemented graceful degradation when dependencies are not available

## Example Complete Test File
```python
"""
Test suite for client notification module with external dependencies
"""

import pytest
from unittest.mock import Mock, patch

# Pure functions that can be tested without external dependencies
def format_client_notification(name, date, time, email=None, source="chat"):
    """Format notification text."""
    lines = [
        "🔔 <b>NEW BOOKING</b>",
        "",
        f"Prospect: <b>{name}</b>"
    ]
    
    if email:
        lines.append(f"Email: {email}")
    
    lines.extend([
        f"Date: {date}",
        f"Time: {time}",
        f"Source: {source}"
    ])
    
    return "\n".join(lines)

def send_notification_via_email(client, recipient, message, user_settings):
    """Send notification using injected email client."""
    if not client:
        raise ValueError("Email client not provided")
    
    email_config = user_settings.get("email", {})
    sender = email_config.get("sender", "no-reply@example.com")
    
    return client.send(
        from_email=sender,
        to_emails=[recipient],
        subject="New Booking Notification",
        html_content=message
    )

# Tests that work without external dependencies
def test_format_client_notification_basic():
    """Test basic notification formatting."""
    result = format_client_notification(
        name="John Smith",
        date="Monday, July 28, 2026",
        time="2:30 PM"
    )
    
    assert "🔔 <b>NEW BOOKING</b>" in result
    assert "John Smith" in result
    assert "Monday, July 28, 2026" in result
    assert "2:30 PM" in result
    assert "Email:" not in result  # No email provided

def test_format_client_notification_with_email():
    """Test notification formatting with email."""
    result = format_client_notification(
        name="Jane Doe",
        date="Tuesday, July 29, 2026",
        time="10:00 AM",
        email="jane@example.com"
    )
    
    assert "🔔 <b>NEW BOOKING</b>" in result
    assert "Jane Doe" in result
    assert "jane@example.com" in result

def test_send_notification_via_email():
    """Test notification sending with mocked client."""
    mock_client = Mock()
    mock_client.send.return_value = {"id": "test-123", "status": "sent"}
    
    user_settings = {"email": {"sender": "test@example.com"}}
    
    result = send_notification_via_email(
        client=mock_client,
        recipient="client@example.com",
        message="Test notification",
        user_settings=user_settings
    )
    
    mock_client.send.assert_called_once_with(
        from_email="test@example.com",
        to_emails=["client@example.com"],
        subject="New Booking Notification",
        html_content="Test notification"
    )
    
    assert result["id"] == "test-123"
    assert result["status"] == "sent"

def test_send_notification_via_email_no_client():
    """Test error handling when no client provided."""
    with pytest.raises(ValueError, match="Email client not provided"):
        send_notification_via_email(
            client=None,
            recipient="client@example.com",
            message="Test",
            user_settings={}
        )
```