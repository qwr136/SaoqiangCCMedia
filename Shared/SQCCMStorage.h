#pragma once
#import <Foundation/Foundation.h>
#import "SQCCMLayoutPolicy.h"
#if defined(THEOS_PACKAGE_SCHEME_ROOTHIDE)
#import <roothide.h>
#endif
static NSString *const SQCCMDomain=@"com.saoqiang.ccmedia";
static NSString *const SQCCMChanged=@"com.saoqiang.ccmedia/changed";
static inline NSString *SQCCMPath(NSString *logical) {
#if defined(THEOS_PACKAGE_SCHEME_ROOTHIDE)
    return jbroot(logical);
#else
    return logical;
#endif
}
static inline NSString *SQCCMConfigPath(void){return SQCCMPath(@"/var/mobile/Library/Preferences/com.saoqiang.ccmedia.plist");}
static inline NSString *SQCCMMediaDirectory(void){return SQCCMPath(@"/var/mobile/Library/Application Support/SaoqiangCCMedia");}
static inline NSError *SQCCMError(NSInteger code,NSString *message){return [NSError errorWithDomain:SQCCMDomain code:code userInfo:@{NSLocalizedDescriptionKey:message?:@"操作失败"}];}
static inline NSDictionary *SQCCMRead(NSError **error){
    NSString *path=SQCCMConfigPath();NSFileManager *fm=NSFileManager.defaultManager;
    if(![fm fileExistsAtPath:path])return [NSUserDefaults.standardUserDefaults persistentDomainForName:SQCCMDomain]?:@{};
    NSData *data=[NSData dataWithContentsOfFile:path options:0 error:error];if(!data)return nil;
    id value=[NSPropertyListSerialization propertyListWithData:data options:NSPropertyListImmutable format:NULL error:error];
    if([value isKindOfClass:NSDictionary.class])return value;
    if(error&&!*error)*error=SQCCMError(1,@"配置损坏，原文件未被覆盖。");return nil;
}
static inline NSArray<NSString *> *SQCCMProfileKeys(void){return @[@"enabled",@"muted",@"autoplay",@"mediaName",@"mediaKind",@"opacity",@"moduleSize"];}
static inline NSDictionary *SQCCMProfile(NSDictionary *root,NSUInteger index){
    NSDictionary *modules=[root[@"modules"] isKindOfClass:NSDictionary.class]?root[@"modules"]:nil;
    id saved=modules[[NSString stringWithFormat:@"%lu",(unsigned long)index]];
    if([saved isKindOfClass:NSDictionary.class])return saved;
    // Legacy values belong only to module 1. An explicitly saved empty profile
    // is authoritative and must never fall back after its media was cleared.
    if(index==1){NSMutableDictionary *old=[NSMutableDictionary new];for(NSString *key in SQCCMProfileKeys())if(root[key])old[key]=root[key];return old;}
    return @{};
}
static inline NSString *SQCCMDisplayName(NSUInteger index){id name=SQCCMProfile(SQCCMRead(NULL),index)[@"customName"];if([name isKindOfClass:NSString.class]&&[name length])return name;return [NSString stringWithFormat:@"视频模块 %lu",(unsigned long)index];}
static inline NSDictionary *SQCCMReplacingProfile(NSDictionary *root,NSUInteger index,NSDictionary *profile){
    NSMutableDictionary *out=root.mutableCopy?:[NSMutableDictionary new];
    NSMutableDictionary *modules=[out[@"modules"] isKindOfClass:NSDictionary.class]?[out[@"modules"] mutableCopy]:[NSMutableDictionary new];
    modules[[NSString stringWithFormat:@"%lu",(unsigned long)index]]=[profile copy];out[@"modules"]=modules;out[@"schemaVersion"]=@2;return out;
}
static inline BOOL SQCCMBool(NSDictionary *config,NSString *key,BOOL fallback){id value=config[key];return [value isKindOfClass:NSNumber.class]?[value boolValue]:fallback;}
static inline double SQCCMOpacity(NSDictionary *profile){id value=profile[@"opacity"];return SQCCMClampOpacity([value isKindOfClass:NSNumber.class]?[value doubleValue]:1);}
static inline NSString *SQCCMMediaPath(NSDictionary *profile){
    id name=profile[@"mediaName"];
    if(![name isKindOfClass:NSString.class]||![name length]||[name length]>180||![name isEqualToString:[name lastPathComponent]]||[name hasPrefix:@"."]||[name rangeOfCharacterFromSet:[NSCharacterSet characterSetWithCharactersInString:@"/\\:"]].location!=NSNotFound)return nil;
    return [SQCCMMediaDirectory() stringByAppendingPathComponent:name];
}
static inline BOOL SQCCMWrite(NSDictionary *config,NSError **error){
    NSCAssert(NSThread.isMainThread,@"The Preferences main queue is the single configuration writer");
    NSFileManager *fm=NSFileManager.defaultManager;
    if(![fm createDirectoryAtPath:SQCCMConfigPath().stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:error])return NO;
    NSData *data=[NSPropertyListSerialization dataWithPropertyList:config format:NSPropertyListBinaryFormat_v1_0 options:0 error:error];
    if(!data||![data writeToFile:SQCCMConfigPath() options:NSDataWritingAtomic error:error])return NO;
    [fm setAttributes:@{NSFilePosixPermissions:@0644} ofItemAtPath:SQCCMConfigPath() error:nil];
    CFNotificationCenterPostNotification(CFNotificationCenterGetDarwinNotifyCenter(),(__bridge CFStringRef)SQCCMChanged,NULL,NULL,YES);return YES;
}
static inline void SQCCMRemoveUnreferenced(NSString *path,NSDictionary *root){
    if(!path)return;for(NSUInteger i=1;i<=6;++i)if([SQCCMMediaPath(SQCCMProfile(root,i)) isEqual:path])return;
    if([path.stringByDeletingLastPathComponent isEqual:SQCCMMediaDirectory()])[NSFileManager.defaultManager removeItemAtPath:path error:nil];
}

static inline CGFloat SQCCMCornerRadius(NSDictionary *profile){id value=profile[@"cornerRadius"];double radius=[value isKindOfClass:NSNumber.class]?[value doubleValue]:22;return isfinite(radius)?MAX(0,MIN(60,radius)):22;}
