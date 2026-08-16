---
name: module-dependency-testing
description: Test modules with external dependencies by isolating core functionality and using dependency injection patterns
category: devops
version: 1.0.0
triggers:
  - Testing Python modules with external dependencies
  - Modules that import libraries not available in test environments
  - Testing code with Google Calendar, Firebase, or other external APIs
  - Writing unit tests for modules with complex setup requirements
references:
  - references/testing-with-external-dependencies.md (in lo-project-standards skill)
---

# Module Dependency Testing

## Purpose
Test modules with external dependencies by extracting core functionality and using dependency injection patterns to enable isolated testing.

## When to Use
- Testing modules that import external libraries (Google Calendar, Firebase, etc.)
- Modules that fail to import in test environments due to missing dependencies
- Code that requires complex setup or credentials for testing
- When direct imports of modules cause test failures

## Key Patterns

### 1. Dependency Isolation
Extract pure functions that can be tested without external dependencies:

```python
# Extract core logic into testable functions
def format_notification_text(name, date_str, time_str, email="", source="chat"):
    """Pure function that can be tested without external dependencies."""
    email_line = f"\nEmail: {email}" if email else ""
    return (
        "🔔 <b>NEW BOOKING</b>\n\n"
        f"Prospect: <b>{name}</b>{email_line}\n"
        f"Date: {date_str}\n"
        f"Time: {time_str}\n"
        f"Source: {source}\n"
    )

# Test the isolated function
def test_notification_formatting():
    result = format_notification_text(
        name="John Doe",
        date_str="Monday, July 28, 2026",
        time_str="10:00 AM",
        email="john@example.com",
        source="chat"
    )
    assert "🔔 <b>NEW BOOKING</b>" in result
    assert "John Doe" in result
    assert "john@example.com" in result
```

### 2. Dependency Injection
Pass dependencies as parameters rather than importing them directly:

```python
# Instead of importing directly in the module
# from google_calendar import CalendarClient  # May not be available in tests

# Use dependency injection
def send_calendar_invitation(client, event_data):
    """Function that accepts client as parameter."""
    return client.create_event(event_data)

# In tests, mock the client
def test_send_calendar_invitation(mocker):
    mock_client = mocker.Mock()
    mock_client.create_event.return_value = {"status": "created"}
    
    result = send_calendar_invitation(mock_client, {"title": "Test"})
    assert result["status"] == "created"
```

### 3. Optional Imports with Graceful Degradation
Handle missing dependencies gracefully:

```python
try:
    from google_calendar import CalendarClient
    _HAS_CALENDAR = True
except ImportError:
    CalendarClient = None
    _HAS_CALENDAR = False

def get_calendar_client():
    if not _HAS_CALENDAR:
        raise ImportError("Google Calendar dependencies not available")
    return CalendarClient()
```

### 4. Test Double Patterns
Create simple implementations that mimic external service behavior:

```python
class MockCalendarClient:
    """Test double for Google Calendar client."""
    def __init__(self):
        self.events = []
    
    def create_event(self, event_data):
        event = {"id": len(self.events), "data": event_data}
        self.events.append(event)
        return event

# Use in tests
def test_calendar_integration():
    client = MockCalendarClient()
    result = send_calendar_invitation(client, {"title": "Test"})
    assert len(client.events) == 1
```

## Implementation Steps

### 1. Identify Core Functionality
1. Review module code to identify pure functions
2. Separate I/O operations from business logic
3. Extract formatting, validation, and calculation functions
4. Document external dependencies

### 2. Create Testable Interfaces
1. Define function signatures that accept dependencies as parameters
2. Create abstract base classes for complex dependencies
3. Implement simple mock versions for testing
4. Ensure all core logic can be tested independently

### 3. Write Isolated Tests
1. Test pure functions with various input combinations
2. Verify error handling and edge cases
3. Test graceful degradation when dependencies are missing
4. Validate integration points with mock dependencies

### 4. Validate Integration
1. Create integration tests with real dependencies when available
2. Use conditional test execution based on environment
3. Test error scenarios with simulated network failures
4. Validate performance and resource usage

## Best Practices

### Test Organization
- Group related tests by functionality
- Use descriptive test names that explain the scenario
- Separate unit tests from integration tests
- Include setup and teardown methods for complex test data

### Dependency Handling
- Always import dependencies inside try/except blocks
- Provide clear error messages when dependencies are missing
- Use feature flags to enable/disable functionality
- Document required dependencies and installation steps

### Testing Strategies
- Write tests for all extracted pure functions
- Mock external services rather than calling them
- Test error conditions and edge cases thoroughly
- Use parametrized tests for multiple scenarios

## Testing Patterns

### Pure Function Testing
```python
def format_client_notification(name, date, time, email=None, source="chat"):
    """
    Format notification text without external dependencies.
    
    Args:
        name (str): Client name
        date (str): Appointment date
        time (str): Appointment time
        email (str, optional): Client email
        source (str): Source of booking
        
    Returns:
        str: Formatted notification text
    """
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

def test_format_client_notification():
    """Test notification formatting without external dependencies."""
    result = format_client_notification(
        name="John Smith",
        date="Monday, July 28, 2026",
        time="2:30 PM",
        email="john@example.com",
        source="chat"
    )
    
    assert "🔔 <b>NEW BOOKING</b>" in result
    assert "John Smith" in result
    assert "john@example.com" in result
    assert "Monday, July 28, 2026" in result
    assert "2:30 PM" in result
    assert "chat" in result
```

### Dependency Injection Testing
```python
def send_notification_via_email(client, recipient, message, user_settings):
    """
    Send notification using injected email client.
    
    Args:
        client: Email client instance
        recipient (str): Recipient email address
        message (str): Message content
        user_settings (dict): User configuration
        
    Returns:
        dict: Response from email service
    """
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

def test_send_notification_via_email(mocker):
    """Test notification sending with mocked email client."""
    # Mock email client
    mock_client = mocker.Mock()
    mock_client.send.return_value = {"id": "test-id", "status": "sent"}
    
    # Test data
    user_settings = {
        "email": {
            "sender": "test@example.com"
        }
    }
    
    # Call function with mocked client
    result = send_notification_via_email(
        client=mock_client,
        recipient="client@example.com",
        message="Test message",
        user_settings=user_settings
    )
    
    # Verify mock was called correctly
    mock_client.send.assert_called_once_with(
        from_email="test@example.com",
        to_emails=["client@example.com"],
        subject="New Booking Notification",
        html_content="Test message"
    )
    
    # Verify result
    assert result["status"] == "sent"
    assert result["id"] == "test-id"
```

## Common Pitfalls

### 1. Direct Imports in Module Level
Avoid importing modules at the module level when they might not be available:

```python
# Bad: Direct import that may fail
# from google_calendar import CalendarClient  # ImportError in test env

# Good: Conditional import with graceful handling
try:
    from google_calendar import CalendarClient
    HAS_CALENDAR = True
except ImportError:
    CalendarClient = None
    HAS_CALENDAR = False

def get_calendar_client():
    """Get calendar client with proper error handling."""
    if not HAS_CALENDAR:
        raise RuntimeError("Google Calendar dependencies not available")
    return CalendarClient()
```

### 2. Complex Setup in Tests
Avoid complex setup that mirrors production environment:

```python
# Bad: Complex setup that's hard to maintain
# def test_calendar_integration():
#     calendar_client = GoogleCalendarClient(
#         credentials_path="/path/to/credentials.json",
#         scopes=["https://www.googleapis.com/auth/calendar"]
#     )
#     # ... more complex setup

# Good: Simple mock that tests the interface
def test_calendar_scheduling():
    mock_client = MockCalendarClient()
    scheduler = AppointmentScheduler(calendar_client=mock_client)
    
    result = scheduler.schedule_appointment(
        name="Test Client",
        date="2026-07-28",
        time="14:30"
    )
    
    assert result is True
    assert len(mock_client.events) == 1
```

### 3. Testing Implementation Details
Focus on testing behavior, not implementation:

```python
# Bad: Testing internal implementation
# assert scheduler._format_date(date) == "formatted_date"

# Good: Testing observable behavior
result = scheduler.format_notification("John", "2026-07-28", "14:30")
assert "John" in result
assert "2026-07-28" in result
```

## Example Test Suite
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