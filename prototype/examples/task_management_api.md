# Task Management API Coding Problem

## Problem Statement
Create a RESTful API for a simple task management system with the following requirements:

### Core Entities
1. **Users**
   - id (UUID, primary key)
   - username (string, unique, required)
   - email (string, unique, required)
   - hashed_password (string, required)
   - created_at (timestamp)
   - updated_at (timestamp)

2. **Tasks**
   - id (UUID, primary key)
   - title (string, required, max 200 chars)
   - description (text, optional)
   - status (enum: 'pending', 'in_progress', 'completed')
   - priority (enum: 'low', 'medium', 'high')
   - due_date (datetime, optional)
   - user_id (foreign key to users)
   - created_at (timestamp)
   - updated_at (timestamp)

### API Endpoints
**Authentication required for all endpoints except /auth/register and /auth/login**

1. **Authentication**
   - POST /auth/register - Register new user
   - POST /auth/login - Login, returns JWT token

2. **Users**
   - GET /users/me - Get current user profile
   - PUT /users/me - Update current user profile
   - DELETE /users/me - Delete current user account

3. **Tasks**
   - GET /tasks - List all tasks for current user (with filtering by status, priority)
   - POST /tasks - Create new task
   - GET /tasks/{id} - Get task details
   - PUT /tasks/{id} - Update task
   - DELETE /tasks/{id} - Delete task
   - GET /tasks/stats - Get task statistics (count by status, priority)

### Technical Requirements
- Use FastAPI framework
- SQLAlchemy ORM with PostgreSQL
- JWT authentication
- Pydantic models for request/response validation
- Alembic for database migrations
- Comprehensive unit tests with pytest
- Environment-based configuration
- Error handling with appropriate HTTP status codes
- Pagination for list endpoints
- Input validation and sanitization

### Non-Functional Requirements
- Code should follow PEP 8 style guide
- Include docstrings for all functions and classes
- Use type hints throughout
- Write tests with >90% coverage
- Include a README with setup instructions
- Dockerize the application

### Acceptance Criteria
1. All endpoints work as specified
2. Proper authentication and authorization
3. Input validation prevents malformed requests
4. Database migrations can be run to set up schema
5. Tests pass and cover critical paths
6. Code is well-organized and modular
7. Error responses are informative and consistent

This is a medium-difficulty problem that requires:
- Database design and migrations
- Authentication implementation
- CRUD operations with relationships
- Testing strategy
- API design best practices
- Error handling
- Configuration management