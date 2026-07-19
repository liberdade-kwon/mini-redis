plugins {
    kotlin("jvm") version "2.3.0"
    application
}

repositories {
    mavenCentral()
}

kotlin {
    jvmToolchain(21)
}

application {
    mainClass.set("miniredis.MainKt")
}

// ./gradlew run 으로 서버 실행 (기본 포트 6379)
tasks.named<JavaExec>("run") {
    standardInput = System.`in`
}
