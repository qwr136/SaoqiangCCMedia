include ../Build.mk
include $(THEOS)/makefiles/common.mk
BUNDLE_NAME = SaoqiangCCMedia SaoqiangCCMedia2 SaoqiangCCMedia3 SaoqiangCCMedia4 SaoqiangCCMedia5 SaoqiangCCMedia6
# Module 1 keeps its original folder, executable and bundle identifier for upgrades.
define SQCCM_MODULE_TARGET
$(1)_FILES = SQCCMModule.m
$(1)_CFLAGS = -fobjc-arc -fblocks -DSQCCM_MODULE_INDEX=$(2)
$(1)_FRAMEWORKS = Foundation UIKit AVFoundation ImageIO QuartzCore CoreMedia CoreGraphics
$(1)_PRIVATE_FRAMEWORKS = ControlCenterUIKit
$(1)_INSTALL_PATH = /Library/ControlCenter/Bundles
$(1)_BUNDLE_EXTENSION = bundle
$(1)_RESOURCE_DIRS = $(3)
$(1)_LIBRARIES = roothide
endef
$(eval $(call SQCCM_MODULE_TARGET,SaoqiangCCMedia,1,Resources))
$(eval $(call SQCCM_MODULE_TARGET,SaoqiangCCMedia2,2,Resources2))
$(eval $(call SQCCM_MODULE_TARGET,SaoqiangCCMedia3,3,Resources3))
$(eval $(call SQCCM_MODULE_TARGET,SaoqiangCCMedia4,4,Resources4))
$(eval $(call SQCCM_MODULE_TARGET,SaoqiangCCMedia5,5,Resources5))
$(eval $(call SQCCM_MODULE_TARGET,SaoqiangCCMedia6,6,Resources6))
include $(THEOS_MAKE_PATH)/bundle.mk
