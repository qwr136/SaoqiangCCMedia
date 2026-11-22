# Shared by the original seven bundle targets; do not relabel Mach-O headers.
TARGET = iphone:clang:16.5:15.0
ARCHS = arm64e
DEBUG ?= 0
FINALPACKAGE ?= 1
THEOS_PACKAGE_SCHEME = roothide
ADDITIONAL_CFLAGS += -DTHEOS_PACKAGE_SCHEME_ROOTHIDE=1
TARGET_CODESIGN_FLAGS = -Hsha256 -S -Cadhoc
