THEOS_PACKAGE_SCHEME ?= roothide
ifneq ($(THEOS_PACKAGE_SCHEME),roothide)
$(error This six-module release requires the RootHide package scheme)
endif
include Build.mk
include $(THEOS)/makefiles/common.mk
SUBPROJECTS += Module Preferences
include $(THEOS_MAKE_PATH)/aggregate.mk
