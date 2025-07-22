import re
from pathlib import Path
from typing import Dict, Set, List

from hamster.code_analysis.model.models import TestingFramework, AssertionType, ParameterType, CleanupType, InputType, \
    TestType

CONTEXT_SEARCH_DEPTH = 100
ANALYSIS_FOLDER = Path('hamster_analysis')
WEB_APPLICATION = ["javax.servlet"]
WEB_API = ["org.springframework", "javax.ws"]
WEB_FRAMEWORKK = ["org.springframework", "org.apache.struts", "io.quarkus.", "io.micronaut."]
COMPONENT_BASED_UI = ["com.vaadin."]
JAVA_EE = ["javax.", "jakarta."]
ANDROID = ["android.", "androidx."]

ASSERTIONS_CATEGORY_MAP: Dict[AssertionType, Dict[TestingFramework, Set[str]]] = {
    AssertionType.TRUTHINESS: {
        TestingFramework.JUNIT5: {
            "assertTrue", "assertFalse",
        },
        TestingFramework.JUNIT4: {
            "assertTrue", "assertFalse",
        },
        TestingFramework.JUNIT3: {
            "assertTrue", "assertFalse",
        },
        TestingFramework.TESTNG: {
            "assertTrue", "assertFalse",
        },
        TestingFramework.ASSERTJ: {
            "isTrue", "isFalse",
        },
        TestingFramework.GOOGLE_TRUTH: {
            "isTrue", "isFalse",
        },
        TestingFramework.HAMCREST: {
            "is", "not", "anything"
        },
        TestingFramework.JAVA_BUILTIN: {
            "assert"
        }
    },
    AssertionType.EQUALITY: {
        TestingFramework.JUNIT5: {
            "assertEquals", "assertNotEquals",
        },
        TestingFramework.JUNIT4: {
            "assertEquals", "assertNotEquals",
        },
        TestingFramework.JUNIT3: {
            "assertEquals",
        },
        TestingFramework.TESTNG: {
            "assertEquals", "assertNotEquals",
        },
        TestingFramework.ASSERTJ: {
            "isEqualTo", "isNotEqualTo", "isEqualByComparingTo", "isNotEqualByComparingTo",
            "usingOverriddenEquals",
            "isEqualToIgnoringGivenFields", "isEqualToComparingOnlyGivenFields", "isEqualToIgnoringNullFields",
            # Conflicting with PROPERTY
            "isEqualToIgnoringCase", "isEqualToNormalizingWhitespace",  # Conflicts with STRING
        },
        TestingFramework.GOOGLE_TRUTH: {
            "isEqualTo", "isNotEqualTo",
        },
        TestingFramework.HAMCREST: {
            "equalTo",  # Conflicts with STRING & COLLECTION
            "equalToIgnoringCase", "equalToIgnoringWhiteSpace",  # Conflicts with STRING
            "comparesEqualTo",
        },
    },
    AssertionType.IDENTITY: {
        TestingFramework.JUNIT5: {
            "assertSame", "assertNotSame", "assertInstanceOf", "assertNotInstanceOf",
        },
        TestingFramework.JUNIT4: {
            "assertSame", "assertNotSame",
        },
        TestingFramework.JUNIT3: {
            "assertSame", "assertNotSame",
        },
        TestingFramework.TESTNG: {
            "assertSame", "assertNotSame",
        },
        TestingFramework.ASSERTJ: {
            "isSameAs", "isNotSameAs", "isInstanceOf", "isExactlyInstanceOf", "isInstanceOfAny", "isOfAnyClassIn",
            "withStrictTypeChecking", "withEqualsForType", "isNotInstanceOf",
        },
        TestingFramework.GOOGLE_TRUTH: {
            "isSameInstanceAs", "isNotSameInstanceAs", "isInstanceOf", "isNotInstanceOf"
        },
        TestingFramework.HAMCREST: {
            "sameInstance", "isA", "instanceOf", "typeCompatibleWith"
        },
    },
    AssertionType.NULLNESS: {
        TestingFramework.JUNIT5: {
            "assertNull", "assertNotNull",
        },
        TestingFramework.JUNIT4: {
            "assertNull", "assertNotNull",
        },
        TestingFramework.JUNIT3: {
            "assertNull", "assertNotNull",
        },
        TestingFramework.TESTNG: {
            "assertNull", "assertNotNull",
        },
        TestingFramework.ASSERTJ: {
            "isNull", "isNotNull",
            "isNullOrEmpty"  # Conflicts with COLLECTION & STRING
        },
        TestingFramework.GOOGLE_TRUTH: {
            "isNull", "isNotNull",
        },
        TestingFramework.HAMCREST: {
            "nullValue", "notNullValue",
        },
    },
    AssertionType.NUMERIC_TOLERANCE: {
        TestingFramework.JUNIT5: {
            "assertEquals", "assertNotEquals",
        },
        TestingFramework.JUNIT4: {
            "assertEquals", "assertNotEquals",
        },
        TestingFramework.JUNIT3: {
            "assertEquals",
        },
        TestingFramework.TESTNG: {
            "assertEquals", "assertNotEquals",
        },
        TestingFramework.ASSERTJ: {
            "isCloseTo", "isNotCloseTo", "isCloseToPercentage", "isNotCloseToPercentage"
        },
        TestingFramework.GOOGLE_TRUTH: {
            "isWithin", "isNotWithin"
        },
        TestingFramework.HAMCREST: {
            "closeTo",
        },
    },
    AssertionType.THROWABLE: {
        TestingFramework.JUNIT5: {
            "assertThrows", "assertThrowsExactly", "assertDoesNotThrow", "fail",
        },
        TestingFramework.JUNIT4: {
            "assertThrows", "fail",
        },
        TestingFramework.JUNIT3: {
            "fail",
        },
        TestingFramework.TESTNG: {
            "fail",
        },
        TestingFramework.ASSERTJ: {
            "assertThatThrownBy", "assertThatExceptionOfType", "assertThatCode", "assertThatIOException",
            "assertThatNoException",  # Conflicts with WRAPPER
            "assertThatIllegalArgumentException", "assertThatNullPointerException", "assertThatIllegalStateException",
            # More conflicts with WRAPPER
            "doesNotThrowAnyException", "hasMessageThat", "hasMessageStartingWith", "hasMessageEndingWith",
            "hasMessageMatching", "hasCauseInstanceOf",
            "hasStackTraceContaining", "hasMessageContaining", "isThrownBy", "hasMessage",
            "withNoCause", "withMessage", "withMessageContaining", "havingRootCause", "hasMessageContainingAll",
            "hasMessageNotContaining", "hasMessageNotContainingAny", "hasRootCause", "hasRootCauseMessage",
            "hasRootCauseInstanceOf", "hasRootCauseExactlyInstanceOf", "havingCause", "hasCause",
            "hasCauseExactlyInstanceOf"
        },
        TestingFramework.GOOGLE_TRUTH: {
            "assertThatThrownBy", "hasMessageThat", "hasCauseThat"
        },
        TestingFramework.HAMCREST: {},
    },
    AssertionType.TIMEOUT: {
        TestingFramework.JUNIT5: {
            "assertTimeout", "assertTimeoutPreemptively",
        },
        TestingFramework.JUNIT4: {},
        TestingFramework.JUNIT3: {},
        TestingFramework.TESTNG: {},
        TestingFramework.ASSERTJ: {},
        TestingFramework.GOOGLE_TRUTH: {},
        TestingFramework.HAMCREST: {},
    },
    AssertionType.COLLECTION: {
        TestingFramework.JUNIT5: {
            "assertArrayEquals", "assertIterableEquals", "assertLinesMatch"
        },
        TestingFramework.JUNIT4: {
            "assertArrayEquals",
        },
        TestingFramework.TESTNG: {
            "assertEqualsNoOrder",
        },
        TestingFramework.ASSERTJ: {
            "isEmpty", "contains", "containsAll",  # Conflicts with built-in methods
            "containsExactly", "containsExactlyInAnyOrder", "containsOnly", "isNotEmpty",
            "hasSize",  # Conflicts with COLLECTION
            "containsAnyOf", "containsNoneOf", "doesNotContain", "hasSameSizeAs",
            "containsNoneOf", "containsSequence", "containsSubsequence", "extracting",
            "filteredOn", "filteredOnNull", "containsOnlyOnce", "singleElement",
            "first", "last", "element", "allMatch", "anyMatch", "noneMatch",
            "isSorted", "isSortedAccordingTo", "isSubsetOf", "doesNotContainSequence",
            "doesNotContainSubsequence", "containsExactlyElementsIn", "containsExactlyInAnyOrderElementsOf",
            "containsExactlyEntriesOf", "containsOnlyNulls", "containsExactlyElementsOf", "isSubsetOf",
            "isEqualTo", "isNotEqualTo",  # Conflicts with STRING, EQUALITY
            "assertThatList", "assertThatSet", "assertThatMap",  # Conflicts with WRAPPER
            "filteredOnAssertions",  # Conflicts with GROUPED
            "isNullOrEmpty"  # Conflicts with STRING & NULLNESS
        },
        TestingFramework.GOOGLE_TRUTH: {
            "isEmpty", "contains",  # Conflicts with built-in methods
            "isNotEmpty", "hasSize", "containsExactly", "containsAnyOf",
            "containsNoneOf", "doesNotContain", "containsAtLeast", "containsExactlyElementsIn", "containsNoDuplicates",
            "containsAtLeastElementsIn", "containsExactlyEntriesIn", "containsNoneIn",
        },
        TestingFramework.HAMCREST: {
            "contains",  # Conflicts with built-in methods
            "equalTo",  # Conflicts with STRING, EQUALITY
            "hasItem", "hasItems", "containsInAnyOrder", "everyItem", "arrayWithSize", "arrayContaining",
            "arrayContainingInAnyOrder", "hasKey", "hasValue", "hasEntry", "empty", "hasSize",
            "containsInRelativeOrder", "emptyArray", "emptyCollectionOf", "emptyIterable", "emptyIterableOf",
            "hasItemInArray", "iterableWithSize",
            "isIn", "isOneOf",  # Both take lists as parameters where the matcher subject is an element
        },
    },
    AssertionType.STRING: {
        TestingFramework.JUNIT5: {
            "assertEquals", "assertNotEquals",
        },
        TestingFramework.JUNIT4: {
            "assertEquals", "assertNotEquals",
        },
        TestingFramework.JUNIT3: {
            "assertEquals",
        },
        TestingFramework.TESTNG: {
            "assertEquals", "assertNotEquals",
        },
        TestingFramework.ASSERTJ: {
            "startsWith", "endsWith", "contains", "matches",  # Conflicts with built-in methods
            "isEqualTo", "isNotEqualTo",  # Conflicts with COLLECTION, EQUALITY
            "containsOnlyOnce",  # Conflicts with COLLECTION
            "isEqualToIgnoringCase", "isEqualToNormalizingWhitespace",  # Conflicts with EQUALITY
            "doesNotContain", "doesNotMatch",
            "hasSize",  # Conflicts with COLLECTION
            "hasToString", "containsIgnoringCase", "containsPattern", "isNotEqualToIgnoringCase",
            "isNotEqualToIgnoringWhitespace", "isNotEqualToNormalizingWhitespace",
            "isSubstringOf", "isEqualToNormalizingNewlines", "isEqualToIgnoringWhitespace",
            "isEqualToIgnoringNewLines",
            "isEmpty", "isNotEmpty", # Conflicts with COLLECTION
            "inUnicode", "inHexadecimal",
            "isBlank", "isNotBlank", "doesNotContainOnlyWhitespaces",
            "isNullOrEmpty",  # Conflicts with COLLECTION & NULLNESS
        },
        TestingFramework.GOOGLE_TRUTH: {
            "startsWith", "endsWith", "contains", "matches",  # Conflicts with built-in methods
            "isEqualTo", "isNotEqualTo", "doesNotContain",
            "doesNotMatch", "containsMatch", "doesNotContainMatch", "ignoringCase", "hasLength",
        },
        TestingFramework.HAMCREST: {
            "startsWith", "endsWith",  # Conflicts with built-in methods
            "containsString",
            "equalTo", "equalToIgnoringCase", "equalToIgnoringWhiteSpace",  # Conficts with EQUALITY
            "matchesPattern", "isEmptyString", "isEmptyOrNullString", "hasToString", "stringContainsInOrder"
        },
    },
    AssertionType.COMPARISON: {
        TestingFramework.JUNIT5: {},
        TestingFramework.JUNIT4: {},
        TestingFramework.JUNIT3: {},
        TestingFramework.TESTNG: {},
        TestingFramework.ASSERTJ: {
            "isGreaterThan", "isGreaterThanOrEqualTo", "isLessThan", "isLessThanOrEqualTo", "isPositive",
            "isNegative", "isZero", "isNotZero", "isBetween", "isStrictlyBetween"
        },
        TestingFramework.GOOGLE_TRUTH: {
            "isGreaterThan", "isLessThan", "isAtLeast", "isAtMost",
        },
        TestingFramework.HAMCREST: {
            "lessThan", "greaterThan", "lessThanOrEqualTo", "greaterThanOrEqualTo", "comparesEqualTo"
        },
    },
    AssertionType.PROPERTY: {
        TestingFramework.JUNIT5: {},
        TestingFramework.JUNIT4: {},
        TestingFramework.JUNIT3: {},
        TestingFramework.TESTNG: {},
        TestingFramework.ASSERTJ: {
            "hasFieldOrProperty", "hasFieldOrPropertyWithValue", "usingRecursiveComparison",
            "usingRecursiveFieldByFieldElementComparator", "ignoringFields", "ignoringFields",
            "ignoringActualNullFields",
            "ignoringFieldsOfTypes", "allFieldsSatisfy", "withEqualsForFields", "hasNullFieldsOrProperties",
            "hasNoNullFieldsOrPropertiesExcept",
            "isPresent", "isEmpty", "isNotPresent",  # For Optional objects
            "assertThatObject",  # Conflicting with WRAPPER
            "isEqualToIgnoringGivenFields", "isEqualToComparingOnlyGivenFields", "isEqualToIgnoringNullFields"
            # Conflicting with EQUALITY
        },
        TestingFramework.GOOGLE_TRUTH: {},
        TestingFramework.HAMCREST: {
            "hasProperty", "hasPropertyWithValue", "samePropertyValueAs", "samePropertyValuesAs"
        },
    },
    AssertionType.GROUPED: {
        TestingFramework.JUNIT5: {
            "assertAll",
        },
        TestingFramework.JUNIT4: {},
        TestingFramework.JUNIT3: {},
        TestingFramework.TESTNG: {
            "assertAll",
        },
        TestingFramework.ASSERTJ: {
            "assertSoftly", "assertAll", "filteredOnAssertions", "anySatisfy", "noneSatisfy"
        },
        TestingFramework.GOOGLE_TRUTH: {},
        TestingFramework.HAMCREST: {
            "allOf", "anyOf", "both", "and", "either", "or"
        },
    },
    AssertionType.WRAPPER: {
        TestingFramework.JUNIT4: {
            "assertThat",  # Is used with Hamcrest matchers
        },
        TestingFramework.ASSERTJ: {
            "assertThat",
            "assertThatThrownBy", "assertThatExceptionOfType", "assertThatCode", "assertThatNoException",
            "assertThatIOException",  # Conflicts with THROWABLE
            "assertThatObject",  # Conflict with PROPERTY
            "assertThatOptional", "assertThatStream", "assertThatFuture", "assertThatCompletableFuture",
            "assertThatList", "assertThatSet", "assertThatMap",  # Conflicts with COLLECTION
            "assertThatIllegalArgumentException", "assertThatNullPointerException", "assertThatIllegalStateException",
            # Conflicts with THROWABLE
        },
        TestingFramework.GOOGLE_TRUTH: {
            "assertThat",
        },
        TestingFramework.HAMCREST: {
            "assertThat",
        }
    },
    AssertionType.UTILITY: {
TestingFramework.JUNIT5: {},
        TestingFramework.JUNIT4: {},
        TestingFramework.JUNIT3: {},
        TestingFramework.TESTNG: {},
        TestingFramework.ASSERTJ: {
            "as"
        },
        TestingFramework.GOOGLE_TRUTH: {
            "withMessage"
        },
        TestingFramework.HAMCREST: {}
    }
}

testing_frameworks_by_type = {
    "Core": [
        "junit3",
        "junit4",
        "junit5",
        "testng",
        "spock",
        "java-builtin"
    ],
    "Assertion": [
        "hamcrest",
        "assertj",
        "google-truth"
    ],
    "Mocking": [
        "mockito",
        "easymock",
        "jmock",
        "jmockit",
        "powermock"
    ],
    "BDD": [
        "cucumber",
        "jbehave",
        "serenity",
        "gauge"
    ],
    "API": [
        "rest-assured",
        "webtestclient",
        "mockmvc"
        "spring-test"
    ],
    "Android": [
        "espresso",
        "ui-automator",
        "robolectric",
        "jetpack",
        "androidx-test",
        "android-test",
        "appium",
        "robotium"
    ],
    "UI": [
        "selenium",
        "selendroid",
        "selenide",
        "playright"
    ],
}

BUILTIN_ASSERTION_COMPLEMENTS: Dict[AssertionType, Set[str]] = {
    AssertionType.EQUALITY: {
        "equals",
    },
    AssertionType.STRING: {
        "startsWith", "endsWith", "equalsIgnoreCase", "substring", "charAt", "matches",
        "isEmpty", "indexOf", "contains", "length",  # Conflicting with COLLECTION
    },
    AssertionType.COLLECTION: {
        "isEmpty", "indexOf", "contains", "length",  # Conflicting with STRING
        "containsAll", "containsKey", "containsValue",
        "lastIndexOf", "size", "get", "keySet", "entrySet", "values",
    },
    AssertionType.PROPERTY: {
        "isPresent", "ifPresent", "anyMatch", "allMatch", "stream"
    }
}

FRAMEWORK_PREFIXES = {
    # JUnit
    "org.junit.jupiter.": TestingFramework.JUNIT5,
    "org.junit.": TestingFramework.JUNIT4,
    "junit.framework.": TestingFramework.JUNIT3,

    # TestNG
    "org.testng.": TestingFramework.TESTNG,

    # BDD/Spock/Cucumber/JBehave
    "spock.lang.": TestingFramework.SPOCK,
    "io.cucumber.": TestingFramework.CUCUMBER,
    "org.jbehave.": TestingFramework.JBEHAVE,
    "net.serenitybdd.": TestingFramework.SERENITY,
    "com.thoughtworks.gauge.": TestingFramework.GAUGE,

    # Mocks
    "org.mockito.": TestingFramework.MOCKITO,
    "org.powermock.": TestingFramework.POWERMOCK,
    "org.easymock.": TestingFramework.EASYMOCK,
    "org.jmockit.": TestingFramework.JMOCKIT,
    "org.jmock.": TestingFramework.JMOCK,

    # Assertions / Hamcrest / Truth
    "org.assertj.": TestingFramework.ASSERTJ,
    "org.hamcrest.": TestingFramework.HAMCREST,
    "com.google.common.truth.": TestingFramework.GOOGLE_TRUTH,
    # # ESPRESSO
    "androidx.test.espresso.": TestingFramework.ESPRESSO,
    #
    # # UI_Automator
    "androidx.test.uiautomator.": TestingFramework.UI_AUTOMATOR,
    # JetPack
    "androidx.lifecycle.": TestingFramework.JETPACK,
    # Robolectic
    "org.robolectric.": TestingFramework.ROBOLECTRIC,
    # Android testing
    "androidx.test.": TestingFramework.ANDROIDX_TEST,
    "android.test.": TestingFramework.ANDROID_TEST,
    "com.robotium": TestingFramework.ROBOTIUM,
    "io.appium": TestingFramework.APPIUM,

    # HTTP testing
    "io.restassured.": TestingFramework.REST_ASSURED,

    "org.springframework.test.web.reactive.server": TestingFramework.WEBTESTCLIENT,
    "org.springframework.test.web.servlet.": TestingFramework.MOCKMVC,
    # Spring test
    "org.springframework.boot.test.": TestingFramework.SPRING_TEST,

    # SELENDROID
    "io.selendroid.": TestingFramework.SELENDROID,

    # SELENIUM
    "org.openqa.selenium.": TestingFramework.SELENIUM,

    # PLAYRIGHT
    "com.microsoft.playwright.": TestingFramework.PLAYRIGHT,

    # SELENIDE
    "com.codeborne.selenide.": TestingFramework.SELENIDE,
    # CYPRESS
    # TESTCAFE
    # PUPPETEER
    # NIGHTWATCH
    # ROBOT_FRAMEWORK
    # WED_DRIVER_IO
}
SORTED_FRAMEWORK_PREFIXES = sorted(
    FRAMEWORK_PREFIXES.items(),
    key=lambda kv: -len(kv[0])
)
BOX_PLOT_TYPES = [TestType.API.value, TestType.UI.value, TestType.LIBRARY.value, TestType.UNIT_MODULE.value, TestType.INTEGRATION.value,
                  TestType.EVOSUITE.value, TestType.ASTER.value]
BDD_TEST_FRAMEWORKS = [TestingFramework.SPOCK,
                       TestingFramework.CUCUMBER,
                       TestingFramework.JBEHAVE,
                       TestingFramework.SERENITY,
                       TestingFramework.GAUGE]
BDD_ANNOTATIONS = ["@Given"]
UI_TEST_FRAMEWORKS = [TestingFramework.SELENDROID,
                      TestingFramework.SELENIUM,
                      TestingFramework.PLAYRIGHT,
                      TestingFramework.SELENIDE]
UI_TEST_FRAMEWORKS_PREFIXES_INVERT = [
    package
    for package, framework in FRAMEWORK_PREFIXES.items()
    if framework in UI_TEST_FRAMEWORKS
]
API_TEST_FRAMEWORKS = [TestingFramework.REST_ASSURED,
                       TestingFramework.WEBTESTCLIENT,
                       TestingFramework.MOCKMVC]

API_TEST_FRAMEWORKS_PREFIXES_INVERT = [
    package
    for package, framework in FRAMEWORK_PREFIXES.items()
    if framework in API_TEST_FRAMEWORKS
]

# Could lower-case when parsing, but for convenience later, including box and primitive types separately
TYPE_TO_PARAMETER_MAP: Dict[str, Dict[ParameterType, Set[str]]] = {
    "Java": {
        ParameterType.STRING: {
            "String",
        },
        ParameterType.NUMBER: {
            "byte", "short", "int", "long", "float", "double", "char",
            "Byte", "Short", "Integer", "Long", "Float", "Double", "Character",
            "BigInteger", "BigDecimal",
        },
        ParameterType.BOOLEAN: {
            "boolean", "Boolean",
        },
        ParameterType.COLLECTION: {
            # type[] with collection
            "List", "Set", "Collection", "Iterable", "Map", "Queue", "Deque", "SortedSet",
            "NavigableSet", "SortedMap", "NavigableMap", "SortedMap", "Stream", "IntStream",
            "LongStream", "DoubleStream", "Iterator", "Enumeration", "Optional"
        },
        ParameterType.CALLABLE: {
            "Callable", "Runnable"
        },
        ParameterType.LAMBDA_EXPRESSION: {},
        ParameterType.CLASS_LITERAL: {},
    },
    "Tree-Sitter": {
        ParameterType.STRING: {
            "string_literal",
            # "integral_type" can conflict here
        },
        ParameterType.NUMBER: {
            "decimal_integer_literal",
            "integral_type",
            # Contains "char" and most of the basic number types -> process based on argument name if in argument
            "floating_point_type",
            "type_identifier",  # Types like "Integer" and "Boolean"
        },
        ParameterType.BOOLEAN: {
            "boolean_type"
        },
        ParameterType.COLLECTION: {
            "generic_type"
        },
        ParameterType.CALLABLE: {
            "method_invocation",
        },
        ParameterType.LAMBDA_EXPRESSION: {
            "lambda_expression",
        },
        ParameterType.CLASS_LITERAL: {
            "class_literal"
        },
        ParameterType.PROPERTY: {
            "field_access"
        },
        ParameterType.UNKNOWN: {}
    }
}

GETTER_METHODS = ['is', 'has', 'get']
TEST_ANNOTATIONS = {
    "@Test", "@ParameterizedTest", "@TestFactory", "@RepeatedTest", "@Given"
}

TREE_SITTER_CALLABLE_TYPES = {
    "method_invocation", "class_instance_creation_expression", "object_creation_expression",
    "lambda_expression", "method_reference", "assert_statement"
}
CLDK_TREE_SITTER_CALLABLE_TYPES = {
    "method_invocation", "class_instance_creation_expression", "object_creation_expression",
}
# Might also consider "explicit_constructor_invocation" and "super_method_invocation" at some point

# Associating method names with resource cleanup verbs
CLEANUP_NAME_PATTERNS = [
    (re.compile(r"^(close|closeQuietly)$", re.I), "close"),
    (re.compile(r"^(shutdown|shutdownNow)$", re.I), "shutdown"),
    (re.compile(r"^(stop|stopAsync)$", re.I), "stop"),
    (re.compile(r"^dispose$", re.I), "dispose"),
    (re.compile(r"^destroy$", re.I), "destroy"),
    (re.compile(r"^disconnect$", re.I), "disconnect"),
    (re.compile(r"^(release|releaseLock)$", re.I), "release"),
    (re.compile(r"^(cleanup|cleanUp)$", re.I), "cleanup"),
    (re.compile(r"^(cancel|abort)$", re.I), "cancel"),
    (re.compile(r"^(terminate|terminateNow)$", re.I), "terminate"),
    (re.compile(r"^teardown$", re.I), "teardown"),
    (re.compile(r"^finalize$", re.I), "finalize"),
    (re.compile(r"^unsubscribe$", re.I), "unsubscribe"),
    (re.compile(r"^(closeAsync|disposeAsync)$", re.I), "asyncDispose"),
    (re.compile(r"^awaitTermination$", re.I), "awaitTermination"),
]

# For fallthrough
CLEANUP_CATEGORY_TO_RECEIVER_SUBSTRING: Dict[CleanupType, Set[str]] = {
    # I/O streams, readers, writers, channels, etc...
    CleanupType.INPUT_OUTPUT: {
        "stream", "reader", "writer", "file", "randomaccess",
        "channel",  # Conflicts with NETWORK
    },
    # Network-related resources (HTTP, sockets, etc...)
    CleanupType.NETWORK: {
        "socket", "server", "http", "websocket",
        "channel"  # Conflicts with I/O
    },
    # Databases and persistence
    CleanupType.DATABASE: {
        "connection", "datasource", "statement", "resultset", "entitymanager", "session",
    },
    # Any current processes
    CleanupType.CONCURRENCY: {
        "executor", "thread", "lock", "semaphore", "process",
    },
    # GUI / graphics toolkits
    CleanupType.USER_INTERFACE: {
        "frame", "window", "dialog", "image"
    }
}

CLEANUP_CATEGORY_TO_PREFIXES: Dict[CleanupType, Set[str]] = {
    # I/O streams, etc...
    CleanupType.INPUT_OUTPUT: {
        "java.io.",
        "java.nio.channels.",
        "org.apache.commons.io.",
        "com.google.common.io.",
        "okio.",
    },
    # HTTP, etc...
    CleanupType.NETWORK: {
        "java.net.",
        "javax.net.ssl.",
        "org.apache.http.",
        "okhttp3.",
        "io.netty.channel.",
        "io.grpc.",
        "javax.ws.rs.client.",
        "org.springframework.web.client.",
    },
    # JDBC, JPA, etc...
    CleanupType.DATABASE: {
        "java.sql.",
        "javax.sql.",
        "com.zaxxer.hikari.",
        "org.apache.commons.dbcp2.",
        "javax.persistence.",
        "org.hibernate.",
        "com.mongodb.client.",
        "org.springframework.data.mongodb.core.",
        "redis.clients.jedis.",
        "org.redisson.",
        "com.datastax.oss.driver.api.core.",
        "org.apache.ibatis.session.",
    },
    # Threads, executors, etc...
    CleanupType.CONCURRENCY: {
        "java.lang.Thread",
        "java.util.concurrent.",
        "org.quartz.",
        "akka.actor.",
        "com.google.common.util.concurrent.",
    },
    # GUI, etc...
    CleanupType.USER_INTERFACE: {
        "java.awt.",
        "javax.swing.",
        "javax.imageio.",
        "javafx.stage.",
        "javafx.scene.",
        "org.eclipse.swt.widgets.",
    }
}

# See how many cases of com.fasterxml.jackson for disambiguating
STRUCTURED_INPUT_MAP: Dict[InputType, Dict[str, List[str]]] = {
    InputType.JSON: {
        "com.fasterxml.jackson.core.JsonFactory": [
            "createParser", # Used for returning JsonParser
        ],
        "com.google.gson.Gson": [
            "fromJson", # Gson.fromJson
        ],
        "com.google.gson.JsonParser": [
            "parseReader"
        ],
        "org.json.JSONObject": [
            "new JSONObject"
        ],
        "org.json.JSONArray": [
            "new JSONArray"
        ],
        "org.json.simple.parser.JSONParser": [
            "parse"
        ],
        "javax.json.Json": [
            "createReader"
        ],
        "javax.json.bind.Jsonb": [
            "fromJson"
        ],
        "com.fasterxml.jackson.databind.ObjectMapper": [ # Ambiguous over YAML, JSON, CSV, or XML (uses the respective Mapper)
            "readValue", # NOTE: Can be YAML or JSON depending on the factory argument in ObjectMapper(...) constructor or whether it is new YAMLMapper()
            "readTree"
        ],
        "com.fasterxml.jackson.databind.ObjectReader": [ # Ambiguous over JSON, YAML, CSV, XML
            "readValue",
            "readValues",
            "readTree"
        ],
    },

    InputType.XML: {
        "javax.xml.parsers.DocumentBuilder": [
            "parse",
        ],
        "java.xml.parsers.SAXParser": [
            "parse",
        ],
        "javax.xml.stream.XMLInputFactory": [
            "createXMLStreamReader",
            "createXMLEventReader"
        ],
        "javax.xml.bind.Unmarshaller": [
            "unmarshal"
        ],
        "javax.xml.bind.JAXB": [
            "unmarshal"
        ],
        "org.dom4j.io.SAXReader": [
            "read"
        ],
        "org.jdom2.input.SAXBuilder": [
            "build"
        ],
        "nu.xom.Builder": [
            "build"
        ],
        "com.thoughtworks.xstream.XStream": [
            "fromXML",
        ],
        "com.fasterxml.jackson.dataformat.xml.XmlMapper": [
            "readValue",
            "readTree"
        ],
        "com.fasterxml.jackson.databind.ObjectMapper": [ # Ambiguous over YAML, JSON, CSV, or XML (uses the respective Mapper)
            "readValue", # NOTE: Can be YAML or JSON depending on the factory argument in ObjectMapper(...) constructor or whether it is new YAMLMapper()
            "readTree"
        ],
        "com.fasterxml.jackson.databind.ObjectReader": [ # Ambiguous over JSON, YAML, CSV, XML
            "readValue",
            "readValues",
            "readTree"
        ],
    },

    InputType.YAML: {
        "org.yaml.snakeyaml.Yaml": [
            "load",
            "loadAll",
            "loadAs",
        ],
        "com.esotericsoftware.yamlbeans.YamlReader": [
            "read"
        ],
        "com.fasterxml.jackson.dataformat.yaml.YAMLMapper": [
            "readValue", # NOTE: Can be YAML or JSON depending on the factory argument in ObjectMapper(...) constructor or whether it is new YAMLMapper()
            "readTree"
        ],
        "com.fasterxml.jackson.databind.ObjectMapper": [ # Ambiguous over YAML, JSON, CSV, or XML (uses the respective Mapper)
            "readValue", # NOTE: Can be YAML or JSON depending on the factory argument in ObjectMapper(...) constructor or whether it is new YAMLMapper()
            "readTree"
        ],
        "com.fasterxml.jackson.databind.ObjectReader": [ # Ambiguous over JSON, YAML, CSV, XML
            "readValue",
            "readValues",
            "readTree"
        ],
    },

    InputType.CSV: {
        "org.apache.commons.csv.CSVParser": [
            "new CSVParser", # Constructor call that processes FileReader into CSV
        ],
        "org.apache.commons.csv.CSVFormat": [
            "parse",
        ],
        "com.opencsv.CSVReader": [
            "new CSVReader",
        ],
        "com.opencsv.CSVReaderBuilder": [
            "new CSVReaderBuilder",
        ],
        "com.opencsv.bean.CsvToBeanBuilder": [
            "new CsvToBeanBuilder"
        ],
        "com.univocity.parsers.csv.CsvParser": [
            "parseAll",
            "beginParsing"
        ],
        "org.supercsv.io.CsvListReader": [
            "new CsvListReader",
        ],
        "org.supercsv.io.CsvBeanReader": [
            "new CsvBeanReader"
        ],
        "com.fasterxml.jackson.dataformat.csv.CsvMapper": [
            "readValue",
            "readTree"
        ],
        "com.fasterxml.jackson.databind.ObjectMapper": [ # Ambiguous over YAML, JSON, CSV, or XML (uses the respective Mapper)
            "readValue", # NOTE: Can be YAML or JSON depending on the factory argument in ObjectMapper(...) constructor or whether it is new YAMLMapper()
            "readTree"
        ],
        "com.fasterxml.jackson.databind.ObjectReader": [ # Ambiguous over JSON, YAML, CSV, XML
            "readValue",
            "readValues",
            "readTree"
        ],
    },

    InputType.PROPERTIES: {
        "java.util.Properties": [
            "load",
            "loadFromXML"
        ],
        "org.apache.commons.configuration.PropertiesConfiguration": [
            "new PropertiesConfiguration"
        ],
        "org.apache.commons.configuration2.builder.fluent.Configurations": [
            "properties",
        ],
        "org.springframework.core.io.support.PropertiesLoaderUtils": [
            "loadProperties",
        ]
    },

    InputType.XLS: {
        "org.apache.poi.hssf.usermodel.HSSFWorkbook": [ # For .xls
            "new HSSFWorkbook",
        ],
        "org.apache.poi.xssf.usermodel.XSSFWorkbook": [ # For .xlsx
            "new XSSFWorkbook",
        ],
        "org.apache.poi.ss.usermodel.WorkbookFactory": [
            "create",
        ],
        "com.alibaba.excel.EasyExcel": [
            "read" # Only for .xlsx
        ],
        "jxl.Workbook": [ # Only for .xls
            "getWorkbook"
        ]
    },

    # Only SQL get operations
    InputType.SQL: {
        "java.sql.Statement": [ # Could be any SQL query
            "executeQuery",
        ],
        "java.sql.PreparedStatement": [
            "executeQuery",
        ],
        "java.sql.CallableStatement": [
            "executeQuery",
        ],
        "javax.persistence": [
            "getResultList",
            "getSingleResult"
        ],
        "org.hibernate.Session": [
            "get",
        ],
        "org.springframework.jdbc.core.JdbcTemplate": [
            "query",
            "queryForList",
            "queryForObject"
        ],
        "org.apache.ibatis.session.SqlSession": [
            "selectList",
            "selectOne",
        ],
        "org.jooq.DSLContext": [
            "fetch",
            "fetchOne",
            "fetchAny",
            "fetchInto",
            "fetchOneInto"
        ]
    },

    InputType.HTML: {
        "org.jsoup.Jsoup": [
            "parse",
            "parseBodyFragment",
        ],
        "net.htmlparser.jericho.Source": [
            "new Source",
        ],
        "org.htmlcleaner.HtmlCleaner": [
            "clean",
        ],
        "org.w3c.tidy.Tidy": [
            "parseDOM",
        ]
    },

    InputType.BINARY: {
        "java.io": [
            "new FileInputStream",
            "new RandomAccessFile"
        ],
        "java.nio.file.Files": [
            "newInputStream",
            "readAllBytes"
        ],
        "java.nio.channels.FileChannel": [
            "open"
        ],
        "java.io.DataInputStream": [
            "new DataInputStream",
        ],
        "org.apache.commons.io.FileUtils": [
            "readFileToByteArray"
        ],
        "org.apache.commons.io.IOUtils": [
            "toByteArray"
        ]
    },

    InputType.SERIALIZED: {
        "java.io.ObjectInputStream": [
            "new ObjectInputStream",
        ],
        "com.esotericsoftware.kryo.Kryo": [
            "readObject"
        ],
        "com.caucho.hessian.io.HessianInput": [
            "new HessianInput"
        ]
    },

    InputType.RESOURCE: {
        "java.lang.Class": [
            "getResource", "getResourceAsStream",
        ],
        "java.lang.ClassLoader": [
            "getResource", "getResources", "getResourceAsStream", "getSystemResource", "getSystemResourceAsStream",
            "getSystemResources",
        ],
        "org.springframework.core.io.ClassPathResource": [
            "new ClassPathResource",
        ],
        "org.springframework.core.io.ResourceLoader": [
            "getResource",
        ]
    }
}