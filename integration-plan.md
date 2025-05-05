# Suna Integration Plan for Incentiv Platform

## Overview

This document outlines the plan to integrate Suna, an open-source generalist AI agent, into the existing Incentiv platform. The integration will add a dedicated research and task automation page to the frontend where users can submit queries that Suna will process and handle.

## Current Architecture

### Incentiv Backend (X-API)

- NestJS-based backend application
- Uses Prisma ORM with a relational database
- Modular structure with separate modules for different functionalities
- Authentication and authorization mechanisms in place
- Connects to various external services

### Incentiv Frontend (X-App)

- React-based frontend application
- Consumes APIs from the backend

## Suna Architecture

Suna consists of four main components:

1. **Backend API**: Python/FastAPI service for REST endpoints, thread management, and LLM integration
2. **Frontend**: Next.js/React application with chat interface
3. **Agent Docker**: Isolated execution environment with browser automation and tool integration
4. **Supabase Database**: For data persistence, authentication, and file storage

## Integration Approach

We'll implement a hybrid integration approach where we:

1. Deploy Suna as a separate service
2. Create a dedicated module in the X-API to interact with Suna's API
3. Add a new page in the X-App frontend to provide a research interface

## Detailed Implementation Plan

### Phase 1: Suna Setup and Deployment

#### 1.1 Set up required infrastructure

##### 1.1.1 Create a Supabase project

- Sign up for Supabase account if not already available
- Create a new project with appropriate region selection
- Configure for service use only (not for end-user authentication)
- Set up database schema based on Suna requirements
- Configure RLS (Row Level Security) policies
- Generate and securely store API keys

##### 1.1.2 Set up Redis instance

- Choose hosting option (self-hosted, cloud provider like Upstash)
- Configure Redis with appropriate memory allocation
- Set up password authentication
- Configure persistence settings
- Set up monitoring and alerts

##### 1.1.3 Create Daytona account for secure agent execution

- Register for Daytona account
- Set up workspace configuration
- Configure image with agent requirements
- Generate API keys and store securely
- Test agent execution capabilities

##### 1.1.4 Obtain necessary API keys

- Create Anthropic account and generate API key
- Set up Tavily account for enhanced search capabilities (optional)
- Register for Firecrawl for web scraping (optional)
- Set up RapidAPI account and subscribe to necessary services (optional)
- Create secure storage for all API keys (secrets manager, vault, etc.)

#### 1.2 Deploy Suna backend

##### 1.2.1 Set up environment

- Clone Suna repository
- Configure environment variables in .env file
- Create Docker configuration (either standalone or Kubernetes)
- Set up CI/CD pipeline for automated deployment

##### 1.2.2 Configure backend settings

- Configure FastAPI settings for production
- Set up rate limiting and API protection
- Configure LLM providers (primarily Anthropic)
- Set up database connection to Supabase
- Configure Redis for caching and session management

##### 1.2.3 Deploy and test

- Deploy backend to staging environment
- Test API endpoints
- Configure logging and monitoring
- Set up alerting for critical errors
- Document API endpoints for integration

#### 1.3 Create a simplified Suna agent configuration

##### 1.3.1 Configure core capabilities

- Set up browser automation with Playwright
- Configure file management capabilities
- Set up search and web scraping tools
- Configure API access permissions

##### 1.3.2 Customize for research focus

- Modify agent prompts for research-specific tasks
- Configure tools specifically for market research, competitor analysis, etc.
- Optimize agent for data extraction and report generation
- Set up templates for common research outputs (presentations, reports, etc.)

##### 1.3.3 Test agent capabilities

- Run test queries for different research scenarios
- Validate browser automation functionality
- Test file creation and manipulation
- Verify result quality and formatting
- Document limitations and capabilities

### Phase 2: Incentiv Backend Integration

#### 2.1 Create a new Suna module in X-API

##### 2.1.1 Set up module structure

- Create directory structure (src/suna/)
- Create module file (suna.module.ts)
- Set up imports and dependencies
- Register module in app.module.ts

##### 2.1.2 Define module interfaces and DTOs

- Create interface definitions for Suna API responses
- Define Data Transfer Objects for research requests
- Create enums for research types and statuses
- Document interface definitions

##### 2.1.3 Configure module settings

- Set up configuration parameters
- Create environment variable definitions
- Configure HTTP client with appropriate timeouts and retry logic
- Set up dependency injection

#### 2.2 Implement Suna service for interacting with Suna API

##### 2.2.1 Create base service implementation

- Implement SunaService class with dependency injection
- Set up HTTP client configuration
- Configure error handling and logging
- Implement retry mechanism for API calls

##### 2.2.2 Implement core methods

- Develop createResearchSession() method
- Implement getResearchResults() method
- Create getResearchStatus() method
- Build helper methods for common operations

##### 2.2.3 Add result transformation and processing

- Create mappers for converting Suna responses to internal models
- Implement data validation and sanitization
- Add caching for frequent requests
- Develop error handling for various API response scenarios

##### 2.2.4 Create testing utilities

- Write unit tests for service methods
- Create mock responses for testing
- Implement integration tests with real API (for staging)
- Document service functionality

#### 2.3 Create API endpoints in X-API

##### 2.3.1 Implement controller

- Create SunaController class
- Register routes and HTTP methods
- Set up route validation and guards
- Implement error handling and responses

##### 2.3.2 Define endpoints

- Create POST /research endpoint for submitting new research
- Implement GET /research/:id for retrieving results
- Develop GET /research/:id/status for checking progress
- Add GET /research endpoint for listing user's research history

##### 2.3.3 Implement request/response handling

- Create request validation
- Implement response transformation
- Set up pagination for list endpoints
- Configure response caching where appropriate

##### 2.3.4 Document API

- Add Swagger documentation
- Create API usage examples
- Document response formats and error codes
- Create internal documentation for developers

#### 2.4 Leverage existing authentication and implement authorization

##### 2.4.1 Integrate with existing auth system

- Use existing x-api authentication mechanisms for user authentication
- Extend existing auth guards to protect research endpoints
- Configure JWT validation to work with research endpoints
- Ensure proper user identification and tracking across the integrated system

##### 2.4.2 Implement service-to-service authentication

- Create secure API key system for x-api to authenticate with Suna service
- Implement request signing for backend-to-backend communication
- Set up token-based authentication between services
- Create rotation mechanisms for service credentials

##### 2.4.3 Create authorization rules

- Implement role-based access control for research functionality
- Configure permission checks for research operations
- Set up team/organization-level permissions
- Create authorization tests

##### 2.4.4 Add rate limiting and quotas

- Implement per-user rate limiting
- Create organization-level quotas
- Set up usage tracking and logging
- Configure throttling for high-volume users

##### 2.4.5 Audit and logging

- Implement comprehensive audit logging
- Create user activity tracking
- Set up security alerts for potential abuse
- Configure compliance reporting if needed

#### 2.5 Create database schema for research history

##### 2.5.1 Define Prisma schema

- Create Research model with required fields
- Set up relations to User model
- Add indexes for frequent queries
- Configure cascade behaviors

##### 2.5.2 Create migrations

- Generate and test database migrations
- Create seed data for testing
- Document schema changes
- Set up migration rollback procedures

##### 2.5.3 Implement repository pattern

- Create ResearchRepository for database operations
- Implement CRUD operations
- Add specialized queries for reporting
- Create transaction support for complex operations

##### 2.5.4 Set up data lifecycle management

- Implement data retention policies
- Create data archiving procedures
- Configure data backup for research results
- Document data lifecycle for compliance

### Phase 3: Frontend Integration

#### 3.1 Create a new Research page in the frontend

##### 3.1.1 Set up page structure

- Create React component files
- Set up routing configuration
- Design component hierarchy
- Implement layout components (container, sidebar, main content)

##### 3.1.2 Design and implement UI

- Create wireframes for research interface
- Implement responsive design for all device sizes
- Design and implement navigation elements
- Create loading states and placeholders

##### 3.1.3 State management

- Set up Redux/Context for research state management
- Implement action creators and reducers
- Create selectors for accessing state
- Set up middleware for async operations

##### 3.1.4 API integration

- Create API client for research endpoints
- Implement error handling and retry logic
- Set up authentication token management
- Create unit tests for API integration

#### 3.2 Implement research submission form

##### 3.2.1 Design form UI

- Create input components for text entry
- Design and implement dropdown selectors for research type
- Create file upload component with drag-and-drop
- Implement form validation UI

##### 3.2.2 Form functionality

- Set up form state management
- Implement validation rules and error display
- Create form submission logic
- Add support for saving draft queries

##### 3.2.3 Enhance user experience

- Add autocomplete for common queries
- Implement suggestion system based on past research
- Create templates for different research types
- Add help text and tooltips for form fields

##### 3.2.4 File upload capabilities

- Implement file upload component
- Add support for multiple file formats
- Create file preview functionality
- Implement file size validation and progress indicators

#### 3.3 Create results visualization

##### 3.3.1 Implement basic results display

- Create components for text results
- Design and implement table components for structured data
- Create card components for entity information
- Implement responsive layouts for different result types

##### 3.3.2 Create data visualizations

- Implement chart components for numeric data
- Create network graph for relationship data
- Design and implement timeline visualizations
- Add map visualizations for geographic data

##### 3.3.3 Add export functionality

- Create PDF export capability
- Implement Excel/CSV export for tabular data
- Add image export for visualizations
- Create presentation export (PowerPoint/Google Slides)

##### 3.3.4 Enhanced viewing options

- Implement filtering and sorting of results
- Create collapsible sections for large results
- Add search functionality within results
- Implement view preferences and saving

#### 3.4 Implement real-time updates

##### 3.4.1 Set up WebSocket connection

- Implement WebSocket client
- Create connection management
- Handle reconnection and error states
- Set up authentication for secure connections

##### 3.4.2 Create progress indicators

- Design and implement progress bar component
- Create step indicator for multi-phase research
- Implement animated indicators for active research
- Add estimated time remaining functionality

##### 3.4.3 Add live result streaming

- Implement incremental result display
- Create animation for new results
- Design and implement notification system
- Add sound alerts (optional, configurable)

##### 3.4.4 Implement background processing

- Create support for minimized research tasks
- Add browser notifications for completed research
- Implement research queue for multiple requests
- Create persistent state across page refreshes

### Phase 4: Security and Performance Considerations

#### 4.1 Implement secure communication

##### 4.1.1 API security

- Implement service API key validation
- Set up HMAC request signing for service-to-service communication
- Ensure secure token exchange between x-api and Suna service
- Implement IP whitelisting for internal services

##### 4.1.2 Configure CORS properly

- Set up allowed origins
- Configure allowed methods and headers
- Implement preflight request handling
- Test cross-origin requests

##### 4.1.3 Secure data transmission

- Ensure all connections use HTTPS
- Implement request and response encryption where needed
- Set up secure headers (HSTS, CSP, etc.)
- Create security audit logging

##### 4.1.4 Authentication hardening

- Implement token rotation
- Create short-lived access tokens
- Set up refresh token mechanism
- Add device fingerprinting for suspicious activity detection

#### 4.2 Add rate limiting and quota management

##### 4.2.1 Implement rate limiting

- Create per-user rate limiting
- Set up IP-based rate limiting for unauthenticated requests
- Implement tiered rate limits based on user roles
- Create rate limit headers in responses

##### 4.2.2 Quota management

- Design quota system (daily/monthly limits)
- Implement usage tracking and storage
- Create quota enforcement mechanism
- Set up notifications for approaching limits

##### 4.2.3 Abuse detection

- Implement detection for suspicious patterns
- Create alerting for potential abuse
- Design automated temporary blocking
- Set up admin interface for managing blocked users

##### 4.2.4 Usage analytics

- Create detailed usage tracking
- Implement analytics dashboard
- Design anomaly detection
- Set up reporting for business intelligence

#### 4.3 Optimize for performance

##### 4.3.1 Implement caching

- Set up Redis caching for common research queries
- Implement browser caching with appropriate headers
- Create cache invalidation strategy
- Configure cache timeouts for different data types

##### 4.3.2 Background processing

- Design queue system for long-running tasks
- Implement worker processes for research tasks
- Create job priority management
- Set up monitoring and alerts for stuck jobs

##### 4.3.3 Database optimization

- Create database indexes for common queries
- Implement query optimization
- Set up connection pooling
- Configure database scaling strategy

##### 4.3.4 Response optimization

- Implement pagination for large result sets
- Create streaming responses for large data
- Optimize payload size with compression
- Implement partial response for mobile clients

### Phase 5: Testing and Deployment

#### 5.1 Develop comprehensive tests

##### 5.1.1 Unit tests

- Create unit tests for all service methods
- Implement controller tests
- Set up repository/data access tests
- Create utility function tests

##### 5.1.2 Integration tests

- Implement API endpoint tests
- Create service integration tests
- Set up database integration tests
- Design cross-module integration tests

##### 5.1.3 End-to-end tests

- Create user flow tests
- Implement UI automation tests
- Set up API sequence tests
- Create performance and load tests

##### 5.1.4 Security tests

- Implement penetration testing
- Create authentication and authorization tests
- Set up data validation and sanitation tests
- Design security regression tests

#### 5.2 Set up staging environment

##### 5.2.1 Infrastructure setup

- Create isolated staging environment
- Set up CI/CD pipeline for staging
- Implement environment-specific configuration
- Create data seeding for testing

##### 5.2.2 Staging Suna instance

- Deploy separate Suna instance for staging
- Configure with test API keys
- Create simulated browser environment
- Set up monitoring for staging

##### 5.2.3 Integration testing

- Implement automated integration tests
- Create manual testing scenarios
- Design user acceptance testing
- Set up performance benchmarking

##### 5.2.4 Load testing

- Create load testing scripts
- Implement performance monitoring
- Set up stress testing
- Design scalability tests

#### 5.3 Deploy to production

##### 5.3.1 Gradual rollout

- Implement feature flags
- Create A/B testing capability
- Design phased rollout plan
- Set up user feedback collection

##### 5.3.2 Monitoring and alerting

- Implement comprehensive monitoring
- Set up error tracking and alerting
- Create performance monitoring dashboard
- Design SLA monitoring and reporting

##### 5.3.3 Documentation and training

- Create user documentation
- Design internal documentation for support
- Implement training materials for users
- Create troubleshooting guides

##### 5.3.4 Continuous improvement

- Set up user feedback loops
- Implement analytics for feature usage
- Create automated performance reporting
- Design iteration plan for enhancements

## Technical Requirements

1. **Infrastructure**:

   - Kubernetes cluster or similar for Suna deployment
   - Supabase account for Suna database
   - Redis instance for caching
   - Daytona account for secure agent execution

2. **API Keys and Services**:

   - Anthropic API key for LLM capabilities
   - Tavily API key for enhanced search (optional)
   - Firecrawl API key for web scraping (optional)
   - RapidAPI key for additional API services (optional)

3. **Development Dependencies**:
   - Python 3.11 for Suna backend
   - Node.js and TypeScript for X-API integration
   - React knowledge for frontend integration

## Timeline and Milestones

1. **Phase 1 (Weeks 1-2)**:

   - Setup infrastructure
   - Deploy Suna
   - Configure agents

2. **Phase 2 (Weeks 3-4)**:

   - Implement X-API integration
   - Create database schema
   - Set up authentication

3. **Phase 3 (Weeks 5-6)**:

   - Develop frontend components
   - Implement user interface
   - Add visualization

4. **Phase 4 (Week 7)**:

   - Implement security measures
   - Add performance optimizations
   - Conduct testing

5. **Phase 5 (Week 8)**:
   - Deploy to staging
   - Test in production-like environment
   - Deploy to production

## Conclusion

This integration plan outlines a comprehensive approach to adding Suna's powerful research and automation capabilities to the Incentiv platform. By implementing this plan, users will gain access to a dedicated research interface that can handle complex queries, perform web research, and generate reports—all seamlessly integrated within the existing platform.

## Next Steps

1. Secure necessary approvals and resources
2. Set up infrastructure components
3. Begin Phase 1 implementation
