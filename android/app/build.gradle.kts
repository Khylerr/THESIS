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
        noCompress += listOf("task", "aislm")
    }
    testOptions {
        unitTests {
            isIncludeAndroidResources = true   // Robolectric screen tests (InferenceScreenTest)
            all {
                it.systemProperty("golden.dir", rootProject.file("../shared/golden").absolutePath)
                it.systemProperty("screens.dir", layout.buildDirectory.dir("inference_screens").get().asFile.absolutePath)
                it.testLogging {
                    events("passed", "failed")
                    exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
                }
            }
        }
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
 * Also the sign classifiers ../shared/models/<id>.aislm (written by models/export_models.py,
 * checked against PyTorch by :core:test); the Inference screen lists every .aislm asset.
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
        rootProject.fileTree("../shared/models") { include("*.aislm") },
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

    // JVM tests of the Inference screen (no phone needed): real layout + drawing via Robolectric
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.14.1")
    testImplementation("androidx.test:core:1.6.1")
}
