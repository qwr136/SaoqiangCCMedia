TARGET = iphone:clang:16.5:15.0
ARCHS = arm64e
DEBUG ?= 0
FINALPACKAGE ?= 1
ifeq ($(THEOS_PACKAGE_SCHEME),roothide)
ADDITIONAL_CFLAGS += -DTHEOS_PACKAGE_SCHEME_ROOTHIDE=1
endif
# RootHide arm64e ABI and explicit ad-hoc signing must match build-native.py.
TARGET_CODESIGN_FLAGS = -Hsha256 -S -Cadhoc
