plugins {
    id("com.android.application")
    id("kotlin-android")
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.example.khaadim"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }

    kotlinOptions {
        jvmTarget = JavaVersion.VERSION_11.toString()
    }

    defaultConfig {
        minSdk = flutter.minSdkVersion
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    flavorDimensions += "app"

    productFlavors {
        create("customer") {
            dimension = "app"
            applicationId = "com.khaadim.customer"
            resValue("string", "app_name", "Khaadim")
        }
        create("kiosk") {
            dimension = "app"
            applicationId = "com.khaadim.kiosk"
            resValue("string", "app_name", "Khaadim Dine-In")
        }
        create("admin") {
            dimension = "app"
            applicationId = "com.khaadim.admin"
            resValue("string", "app_name", "Khaadim Admin")
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

flutter {
    source = "../.."
}