from __future__ import annotations

from enum import Enum
from typing import List, Any, Union, Optional

from pydantic import BaseModel, Field


class AppType(Enum):
    WEB_APPLICATION = "web-application"
    WEB_API = "web-api"
    JAVA_SE = "java-se"
    JAVA_EE = "java-ee"
    ANDROID = "android"


class ExecutionOrder(Enum):
    BEFORE_EACH_TEST = "before-each-test"
    BEFORE_CLASS = "before-class"
    AFTER_EACH_TEST = "after-each-test"
    AFTER_CLASS = "after-class"

class CleanupType(Enum):
    INPUT_OUTPUT = "input-output"
    NETWORK = "network"
    DATABASE = "database"
    CONCURRENCY = "concurrency"
    USER_INTERFACE = "user-interface"
    UNKNOWN = "unknown"


class TestType(Enum):
    UNIT = "unit"
    UNIT_MODULE = "unit-module"
    INTEGRATION = "integration"
    UI = "ui"
    API = "api"
    LIBRARY = "library"
    UNKNOWN = "unknown"
    EVOSUITE = "evosuite"
    ASTER = "aster"


class TestingFramework(Enum):
    HAMCREST = "hamcrest"
    JUNIT3 = "junit3"
    JUNIT4 = "junit4"
    JUNIT5 = "junit5"
    TESTNG = "testng"
    MOCKITO = "mockito"
    ASSERTJ = "assertj"
    GOOGLE_TRUTH = "google-truth"
    SPRING_TEST = "spring-test"
    SPOCK = "spock"
    CUCUMBER = "cucumber"
    JBEHAVE = "jbehave"
    SERENITY = "serenity"
    GAUGE = "gauge"
    POWERMOCK = "powermock"
    EASYMOCK = "easymock"
    JMOCKIT = "jmockit"
    JMOCK = "jmock"
    REST_ASSURED = "rest-assured"
    WEBTESTCLIENT = "webtestclient"
    MOCKMVC = "mockmvc"
    ESPRESSO = "espresso" # Part of Androidx
    UI_AUTOMATOR = "ui-automator" # Part of Androidx
    ROBOLECTRIC = "robolectric"
    JETPACK = "jetpack"
    ANDROIDX_TEST = "androidx-test"
    ANDROID_TEST = "android-test"
    ROBOTIUM = "roboitum"
    APPIUM = "appium"

    SELENDROID = "selendroid"
    SELENIUM = "selenium"
    SELENIDE = "selenide"
    PLAYRIGHT = "playright"
    # CYPRESS = "cypress" # Only with JS
    # TESTCAFE = "testcafe" # Only with JS
    # PUPPETEER = "puppeteer" # Only with JS
    # NIGHTWATCH = "nightwatch" # Only with JS
    # ROBOT_FRAMEWORK = "robot-framework" # Only with JS
    # WED_DRIVER_IO = "wed-driver-io" # Only with JS
    JAVA_BUILTIN = "java-builtin"


class MockingFramework(Enum):
    MOCKITO = "mockito"
    EASY_MOCK = "easy-mock"
    POWER_MOCK = "power-mock"
    WIRE_MOCK = "wire-mock"
    MOCK_SERVER = "mock-server"
    SPRING_TEST = "spring-test"
    JAVA_REFLECTION = "java-reflection"


class AssertionType(Enum):
    TRUTHINESS = "truthiness"
    EQUALITY = "equality"
    IDENTITY = "identity"
    NULLNESS = "nullness"
    NUMERIC_TOLERANCE = "numeric-tolerance"
    THROWABLE = "throwable"
    TIMEOUT = "timeout"
    COLLECTION = "collection"
    STRING = "string"
    COMPARISON = "comparison"
    TYPE = "type"
    GROUPED = "grouped"
    PROPERTY = "property"
    WRAPPER = "wrapper"  # For assertThat
    UTILITY = "utility"  # For things like assigning assertion returns ("as" in AssertJ)

class MockedResource(Enum):
    DB = "db"
    FILE = "file"
    APPLICATION_CLASS = "application-class"
    LIBRARY_CLASS = "library-class"
    SERVICE = "service"

class AssertionDetails(BaseModel):
    """Represents information about an assertion."""
    assertion_type: List[AssertionType]
    assertion_name: str
    assertion_code: str | None
    argument_types: List[Any]
    in_helper: bool | None = None
    is_wrapped: bool | None = None

class CallableDetails(BaseModel):
    """Represents information about a method/constructor call."""
    method_name: str
    argument_types: List[str] = []
    receiver_type: str | None = None
    method_code: str | None = None
    secondary_assertion: bool = False
    is_helper: bool = False

class CleanupDetails(CallableDetails):
    """Represents information about a cleanup method call."""
    receiver_type: str
    canonical_cleanup_method: str
    cleanup_type: List[CleanupType] | None

class InputType(Enum):
    PROPERTIES = "properties" # java.util.Properties
    YAML = "yaml"
    JSON = "json"
    XML = "xml"
    SQL = "sql"
    CSV = "csv"
    XLS = "xls"
    HTML = "html"
    BINARY = "binary"
    SERIALIZED = "serialized"
    RESOURCE = "resource" # Classpath-based resources

class TestInput(BaseModel):
    """Represents information about a test input."""
    method_name: str = ""
    method_signature: str = ""
    receiver_type: str | None = None
    receiver_expr: str | None = None
    input_type: List[InputType] | None = None

class CallAndAssertionSequenceDetails(BaseModel):
    """Represents information about call and assertion sequences"""
    call_sequence_details: List[CallableDetails] = []
    assertion_details: List[AssertionDetails] = []

class FixtureAnalysis(BaseModel):
    """Shared properties for setup and teardown analysis."""
    qualified_class_name: str = ""
    method_signature: str
    ncloc: int = 0
    ncloc_with_helpers: int = 0
    cyclomatic_complexity: int = 0
    cyclomatic_complexity_with_helpers: int = 0
    number_of_objects_created: int = 0
    code: str | None = None
    annotations: List[str] | None = None
    execution_order: ExecutionOrder | None = None
    constructor_call_details: List[CallableDetails] | None = None
    application_call_details: List[CallableDetails] | None = None
    library_call_details: List[CallableDetails] | None = None

class SetupAnalysis(FixtureAnalysis):
    """Represents information about test setup."""
    number_of_mocks_created: int = 0
    mocking_frameworks_used: List[MockingFramework] | None = None
    mocked_resources: List[MockedResource] | None = None
    test_inputs: List[TestInput] | None = None

class TeardownAnalysis(FixtureAnalysis):
    """Represents information about test teardown."""
    number_of_assertions: int = 0
    number_of_cleanup_calls: int = 0 # Tracks operation halts (.stop()), file connection release (.close()), etc...
    cleanup_details: List[CleanupDetails] | None = None

class FocalClass(BaseModel):
    """Represents a focal class"""
    focal_class: str | None = None
    focal_method_names: List[str] | None = None

class TestMethodAnalysis(BaseModel):
    """Represents information about a test method."""
    qualified_class_name: str
    method_signature: str
    method_declaration: str
    annotations: List[str] | None = None
    thrown_exceptions: List[str] | None = None
    test_type: TestType
    ncloc: int
    ncloc_with_helpers: int = 0
    cyclomatic_complexity: int = 0
    cyclomatic_complexity_with_helpers: int = 0
    test_inputs: List[TestInput] | None = None
    is_mocking_used: bool = False
    number_of_mocks_created: int = 0
    mocking_frameworks_used: List[MockingFramework] | None = None
    mocked_resources: List[MockedResource] | None = None
    number_of_objects_created: int = 0
    number_of_helper_methods: int = 0
    helper_method_ncloc: int = 0
    constructor_call_details: List[CallableDetails] | None = None
    application_call_details: List[CallableDetails] | None = None
    library_call_details: List[CallableDetails] | None = None
    call_assertion_sequences: List[CallAndAssertionSequenceDetails] | None = None
    is_bdd: bool = False
    focal_classes: List[FocalClass] | None = None

class TestClassAnalysis(BaseModel):
    """Represents information about a test class."""
    qualified_class_name: str
    testing_frameworks: List[TestingFramework]
    setup_analyses: List[SetupAnalysis] | None = None
    teardown_analyses: List[TeardownAnalysis] | None = None
    test_method_analyses: List[TestMethodAnalysis]
    is_order_dependent: bool = False
    is_bdd: bool = False


class ProjectAnalysis(BaseModel):
    """Represents all analysis information about a Java application."""
    dataset_name: str
    application_class_count: int
    application_method_count: int
    application_cyclomatic_complexity: int
    application_types: List[AppType]
    test_class_analyses: List[TestClassAnalysis]

class ParameterType(Enum):
    """Defines the available types for parameters to be classified in assertions."""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    COLLECTION = "collection"
    CALLABLE = "callable"
    LAMBDA_EXPRESSION = "lambda-expression"
    CLASS_LITERAL = "class-literal"
    PROPERTY = "property"
    CUSTOM = "custom"
    UNKNOWN = "unknown"
