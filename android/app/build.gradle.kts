import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// MUST equal "mediapipe_version" in shared/mediapipe_config.json and the Python venv's
// mediapipe version (the app refuses to start otherwise). Bump all three together.
val mediapipeVersion = "0.10.14"
val cameraxVersion = "1.4.1"

android {
    namespace = "com.aisla.app"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.aisla.app"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        buildConfigField("String", "MEDIAPIPE_VERSION", "\"$mediapipeVersion\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    buildFeatures {
        buildConfig = true
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    androidResources {
        noCompress += "task"
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

/**
 * Bundles the SAME files the Python recorder uses (no copies in this repo, so they cannot
 * drift apart): ../MediaPipe/hand_landmarker.task and ../shared/mediapipe_config.json.
 * At start-up the app checks the model's sha256 against the config, like fslRecorder.py does.
 */
abstract class SharedAssetsTask : DefaultTask() {
    @get:InputFiles
    @get:PathSensitive(PathSensitivity.NAME_ONLY)
    abstract val sources: ConfigurableFileCollection

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun copyFiles() {
        val out = outputDir.get().asFile
        out.deleteRecursively()
        out.mkdirs()
        for (f in sources.files) {
            if (!f.isFile) throw GradleException("Missing shared asset: $f")
            f.copyTo(File(out, f.name), overwrite = true)
        }
    }
}

val sharedAssets = tasks.register<SharedAssetsTask>("sharedAssets") {
    sources.from(
        rootProject.file("../MediaPipe/hand_landmarker.task"),
        rootProject.file("../shared/mediapipe_config.json"),
    )
}

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(sharedAssets, SharedAssetsTask::outputDir)
    }
}

dependencies {
    implementation(project(":core"))

    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.3")

    implementation("androidx.camera:camera-core:$cameraxVersion")
    implementation("androidx.camera:camera-camera2:$cameraxVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraxVersion")
    implementation("androidx.camera:camera-view:$cameraxVersion")

    implementation("com.google.mediapipe:tasks-vision:$mediapipeVersion")
}
