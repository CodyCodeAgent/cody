---
name: java
description: Manage Java projects with Maven or Gradle, including build, test, dependency management, Spring Boot, and JUnit. Use when working with Java code.
metadata:
  author: cody
  version: "1.0"
compatibility: Requires java JDK, maven or gradle
---

# Java Project Management

Manage Java projects with Maven or Gradle, including build, test, and dependency management.

## Prerequisites

- Java JDK must be installed: `java --version`
- Maven: `mvn --version` or Gradle: `gradle --version`

## Maven Projects

### Create a project
```bash
mvn archetype:generate \
  -DgroupId=com.example \
  -DartifactId=my-app \
  -DarchetypeArtifactId=maven-archetype-quickstart \
  -DinteractiveMode=false
```

### Project structure
```
my-app/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/
│   │   └── resources/
│   └── test/
│       ├── java/com/example/
│       └── resources/
└── target/                  # Build output
```

### Build & Run
```bash
mvn compile                  # Compile
mvn package                  # Build JAR
mvn package -DskipTests      # Skip tests
mvn exec:java -Dexec.mainClass="com.example.App"  # Run
java -jar target/my-app-1.0.jar  # Run JAR
```

### Testing
```bash
mvn test                     # Run all tests
mvn test -Dtest=MyTest       # Run specific test
mvn test -Dtest=MyTest#method  # Run specific method
mvn verify                   # Run integration tests
mvn surefire-report:report   # Generate test report
```

### Dependency management (pom.xml)
```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
        <version>3.2.0</version>
    </dependency>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.10.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

```bash
mvn dependency:tree           # View dependency tree
mvn versions:display-dependency-updates  # Check updates
```

## Gradle Projects

### Create a project
```bash
gradle init --type java-application
```

### Build & Run
```bash
gradle build                 # Build
gradle run                   # Run
gradle build -x test         # Skip tests
gradle jar                   # Build JAR
```

### Testing
```bash
gradle test                  # Run all tests
gradle test --tests "MyTest"  # Run specific test
gradle test --tests "MyTest.method"  # Specific method
```

### Dependencies (build.gradle.kts)
```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web:3.2.0")
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.0")
}
```

```bash
gradle dependencies          # View dependency tree
```

## Common Frameworks

### Spring Boot
```bash
# Using Spring Initializr CLI
curl https://start.spring.io/starter.zip \
  -d dependencies=web,data-jpa,h2 \
  -d type=maven-project \
  -d language=java \
  -d javaVersion=21 \
  -o myproject.zip
```

### Test with JUnit 5
```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MyTest {
    @Test
    void shouldAddNumbers() {
        assertEquals(5, Calculator.add(2, 3));
    }

    @Test
    void shouldThrowOnNull() {
        assertThrows(NullPointerException.class, () -> {
            process(null);
        });
    }
}
```

### Test with Mockito
```java
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class ServiceTest {
    @Mock
    private Repository repo;

    @InjectMocks
    private Service service;

    @Test
    void shouldFindUser() {
        when(repo.findById(1L)).thenReturn(Optional.of(new User("Alice")));
        User user = service.getUser(1L);
        assertEquals("Alice", user.getName());
    }
}
```

## Code Quality

### Checkstyle
```bash
mvn checkstyle:check
```

### SpotBugs
```bash
mvn spotbugs:check
```

### Formatting (google-java-format)
```bash
java -jar google-java-format.jar --replace src/**/*.java
```

## Packaging & Distribution

### Fat JAR (Maven Shade Plugin)
```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.5.0</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals><goal>shade</goal></goals>
        </execution>
    </executions>
</plugin>
```

### Spring Boot JAR
```bash
mvn spring-boot:repackage
java -jar target/my-app-1.0.jar
```

## Notes

- Use Java 17+ for new projects (LTS)
- Prefer `record` types for DTOs (Java 16+)
- Use `var` for local variables when type is obvious (Java 10+)
- Always add `test` scope for test-only dependencies
- Use `mvn dependency:tree` to debug dependency conflicts
- Add `target/`, `build/`, `.gradle/` to `.gitignore`
