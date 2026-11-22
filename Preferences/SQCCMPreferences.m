#import <Preferences/PSListController.h>
#import <Preferences/PSSpecifier.h>
#import <Preferences/PSTableCell.h>
#import <PhotosUI/PhotosUI.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <AVFoundation/AVFoundation.h>
#import <ImageIO/ImageIO.h>
#import "../Shared/SQCCMStorage.h"
#define SQCCM_VIDEO_SOURCE_CLASS SQCCMPrefsVideoSource
#import "../Shared/SQCCMVideoSource.h"
#include <math.h>

@interface SQCCMModulePreferences : PSListController <PHPickerViewControllerDelegate,UIDocumentPickerDelegate,UIAdaptivePresentationControllerDelegate>
@property(nonatomic) BOOL sqccmImporting;
@property(nonatomic) BOOL sqccmPicking;
@property(nonatomic,strong) NSURL *sqccmTemporaryURL;
@property(nonatomic,strong) SQCCMPrefsVideoSource *sqccmValidationSource;
@property(nonatomic,strong) AVURLAsset *sqccmValidationAsset;
@property(nonatomic) NSUInteger sqccmImportGeneration;
@property(nonatomic) BOOL sqccmProviderLoading;
@property(nonatomic) BOOL sqccmValidating;
@property(nonatomic,strong) NSProgress *sqccmProviderProgress;
- (NSUInteger)sqccmModuleIndex;
- (void)sqccmAlert:(NSString *)message;
- (void)sqccmChooseSize;
- (BOOL)sqccmStore:(id)value key:(NSString *)key;
- (void)sqccmOpacityChanged:(float)value;
- (void)sqccmFinishFile:(NSString *)file temporary:(NSString *)temporary video:(BOOL)video error:(NSError *)error generation:(NSUInteger)generation;
@end
@interface SQCCMSizePicker : UITableViewController
@property(nonatomic,weak) SQCCMModulePreferences *sqccmOwner;
@end
static NSArray<NSString *> *SQCCMSizeKeys(void){return @[@"1x1",@"2x1",@"1x3",@"1x4",@"2x4",@"4x4",@"3x4",@"2x2"];}
static NSArray<NSString *> *SQCCMSizeNames(void){return @[@"1×1",@"2×1",@"1×3",@"1×4",@"2×4",@"4×4",@"3×4",@"2×2"];}
@implementation SQCCMSizePicker
- (void)viewDidLoad{[super viewDidLoad];self.title=@"模块尺寸（宽×高）";}
- (NSInteger)tableView:(UITableView *)view numberOfRowsInSection:(NSInteger)section{(void)view;(void)section;return SQCCMSizeKeys().count;}
- (UITableViewCell *)tableView:(UITableView *)table cellForRowAtIndexPath:(NSIndexPath *)index{
    UITableViewCell *cell=[table dequeueReusableCellWithIdentifier:@"SQCCM.size"]?:[[UITableViewCell alloc]initWithStyle:UITableViewCellStyleDefault reuseIdentifier:@"SQCCM.size"];
    cell.textLabel.text=SQCCMSizeNames()[index.row];NSString *selected=SQCCMProfile(SQCCMRead(NULL),self.sqccmOwner.sqccmModuleIndex)[@"moduleSize"]?:@"2x2";
    cell.accessoryType=[selected isEqual:SQCCMSizeKeys()[index.row]]?UITableViewCellAccessoryCheckmark:UITableViewCellAccessoryNone;return cell;
}
- (void)tableView:(UITableView *)table didSelectRowAtIndexPath:(NSIndexPath *)index{
    [table deselectRowAtIndexPath:index animated:YES];if(![self.sqccmOwner sqccmStore:SQCCMSizeKeys()[index.row] key:@"moduleSize"])return;
    CFNotificationCenterPostNotification(CFNotificationCenterGetDarwinNotifyCenter(),CFSTR("com.opa334.ccsupport/ReloadSizes"),NULL,NULL,YES);
    [table reloadData];[self.navigationController popViewControllerAnimated:YES];
}
@end
@interface SQCCMOpacityCell : PSTableCell
@property(nonatomic,weak) SQCCMModulePreferences *sqccmOwner;
@end
@implementation SQCCMOpacityCell{
    UISlider *_sqccmSlider;UILabel *_sqccmPercent;
}
- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString *)reuse specifier:(PSSpecifier *)specifier{
    if((self=[super initWithStyle:style reuseIdentifier:reuse specifier:specifier])){
        self.textLabel.text=nil;UILabel *label=[UILabel new];label.text=@"不透明度";label.font=[UIFont systemFontOfSize:15];label.translatesAutoresizingMaskIntoConstraints=NO;
        _sqccmSlider=[UISlider new];_sqccmSlider.minimumValue=0;_sqccmSlider.maximumValue=1;_sqccmSlider.translatesAutoresizingMaskIntoConstraints=NO;_sqccmSlider.accessibilityLabel=@"模块不透明度";
        [_sqccmSlider addTarget:self action:@selector(sqccmUpdate:) forControlEvents:UIControlEventValueChanged];
        [_sqccmSlider addTarget:self action:@selector(sqccmCommit:) forControlEvents:UIControlEventTouchUpInside|UIControlEventTouchUpOutside|UIControlEventTouchCancel];
        _sqccmPercent=[UILabel new];_sqccmPercent.font=[UIFont monospacedDigitSystemFontOfSize:14 weight:UIFontWeightRegular];_sqccmPercent.textAlignment=NSTextAlignmentRight;_sqccmPercent.translatesAutoresizingMaskIntoConstraints=NO;
        for(UIView *v in @[label,_sqccmSlider,_sqccmPercent])[self.contentView addSubview:v];
        [NSLayoutConstraint activateConstraints:@[[label.leadingAnchor constraintEqualToAnchor:self.contentView.leadingAnchor constant:15],[label.widthAnchor constraintEqualToConstant:74],[label.centerYAnchor constraintEqualToAnchor:self.contentView.centerYAnchor],[_sqccmSlider.leadingAnchor constraintEqualToAnchor:label.trailingAnchor constant:8],[_sqccmSlider.centerYAnchor constraintEqualToAnchor:label.centerYAnchor],[_sqccmPercent.leadingAnchor constraintEqualToAnchor:_sqccmSlider.trailingAnchor constant:8],[_sqccmPercent.widthAnchor constraintEqualToConstant:48],[_sqccmPercent.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor constant:-15],[_sqccmPercent.centerYAnchor constraintEqualToAnchor:label.centerYAnchor]]];
        [self refreshCellContentsWithSpecifier:specifier];
    }return self;
}
- (void)refreshCellContentsWithSpecifier:(PSSpecifier *)specifier{
    [super refreshCellContentsWithSpecifier:specifier];self.textLabel.text=nil;self.textLabel.hidden=YES;self.detailTextLabel.text=nil;self.detailTextLabel.hidden=YES;id target=specifier.target;if([target isKindOfClass:SQCCMModulePreferences.class])self.sqccmOwner=target;
    if(_sqccmSlider){_sqccmSlider.value=SQCCMOpacity(SQCCMProfile(SQCCMRead(NULL),self.sqccmOwner.sqccmModuleIndex));_sqccmPercent.text=[NSString stringWithFormat:@"%.0f%%",_sqccmSlider.value*100];}
}
- (void)prepareForReuse{[super prepareForReuse];self.sqccmOwner=nil;}
- (void)sqccmUpdate:(UISlider *)sender{_sqccmPercent.text=[NSString stringWithFormat:@"%.0f%%",sender.value*100];if(UIAccessibilityIsVoiceOverRunning())[self sqccmCommit:sender];}
- (void)sqccmCommit:(UISlider *)sender{[self.sqccmOwner sqccmOpacityChanged:sender.value];}
@end

@interface SQCCMCornerCell : PSTableCell
@property(nonatomic,weak) SQCCMModulePreferences *sqccmOwner;
@end
@implementation SQCCMCornerCell{
    UISlider *_sqccmSlider;UILabel *_sqccmPercent;
}
- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString *)reuse specifier:(PSSpecifier *)specifier{
    if((self=[super initWithStyle:style reuseIdentifier:reuse specifier:specifier])){
        self.textLabel.text=nil;UILabel *label=[UILabel new];label.text=@"模块圆角";label.font=[UIFont systemFontOfSize:15];label.translatesAutoresizingMaskIntoConstraints=NO;
        _sqccmSlider=[UISlider new];_sqccmSlider.minimumValue=0;_sqccmSlider.maximumValue=60;_sqccmSlider.translatesAutoresizingMaskIntoConstraints=NO;_sqccmSlider.accessibilityLabel=@"模块圆角";
        [_sqccmSlider addTarget:self action:@selector(sqccmUpdate:) forControlEvents:UIControlEventValueChanged];
        [_sqccmSlider addTarget:self action:@selector(sqccmCommit:) forControlEvents:UIControlEventTouchUpInside|UIControlEventTouchUpOutside|UIControlEventTouchCancel];
        _sqccmPercent=[UILabel new];_sqccmPercent.font=[UIFont monospacedDigitSystemFontOfSize:14 weight:UIFontWeightRegular];_sqccmPercent.textAlignment=NSTextAlignmentRight;_sqccmPercent.translatesAutoresizingMaskIntoConstraints=NO;
        for(UIView *v in @[label,_sqccmSlider,_sqccmPercent])[self.contentView addSubview:v];
        [NSLayoutConstraint activateConstraints:@[[label.leadingAnchor constraintEqualToAnchor:self.contentView.leadingAnchor constant:15],[label.widthAnchor constraintEqualToConstant:74],[label.centerYAnchor constraintEqualToAnchor:self.contentView.centerYAnchor],[_sqccmSlider.leadingAnchor constraintEqualToAnchor:label.trailingAnchor constant:8],[_sqccmSlider.centerYAnchor constraintEqualToAnchor:label.centerYAnchor],[_sqccmPercent.leadingAnchor constraintEqualToAnchor:_sqccmSlider.trailingAnchor constant:8],[_sqccmPercent.widthAnchor constraintEqualToConstant:48],[_sqccmPercent.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor constant:-15],[_sqccmPercent.centerYAnchor constraintEqualToAnchor:label.centerYAnchor]]];
        [self refreshCellContentsWithSpecifier:specifier];
    }return self;
}
- (void)refreshCellContentsWithSpecifier:(PSSpecifier *)specifier{
    [super refreshCellContentsWithSpecifier:specifier];self.textLabel.text=nil;self.textLabel.hidden=YES;self.detailTextLabel.text=nil;self.detailTextLabel.hidden=YES;id target=specifier.target;if([target isKindOfClass:SQCCMModulePreferences.class])self.sqccmOwner=target;
    if(_sqccmSlider){_sqccmSlider.value=SQCCMCornerRadius(SQCCMProfile(SQCCMRead(NULL),self.sqccmOwner.sqccmModuleIndex));_sqccmPercent.text=[NSString stringWithFormat:@"%.0f pt",_sqccmSlider.value];}
}
- (void)prepareForReuse{[super prepareForReuse];self.sqccmOwner=nil;}
- (void)sqccmUpdate:(UISlider *)sender{_sqccmPercent.text=[NSString stringWithFormat:@"%.0f pt",sender.value];if(UIAccessibilityIsVoiceOverRunning())[self sqccmCommit:sender];}
- (void)sqccmCommit:(UISlider *)sender{[self.sqccmOwner sqccmStore:@(sender.value) key:@"cornerRadius"];}
@end

@interface SQCCMPreferencesController : PSListController @end
static UITableView *SQCCMFindTable(UIView *view){
 if([view isKindOfClass:UITableView.class])return (UITableView *)view;
 for(UIView *child in view.subviews){UITableView *table=SQCCMFindTable(child);if(table)return table;}return nil;
}
static void SQCCMDecorate(PSListController *owner){
 UITableView *table=SQCCMFindTable(owner.view);if(!table)return;table.backgroundColor=UIColor.systemGroupedBackgroundColor;table.separatorStyle=UITableViewCellSeparatorStyleSingleLine;
 UIView *header=[[UIView alloc]initWithFrame:CGRectMake(0,0,table.bounds.size.width,238)];header.autoresizingMask=UIViewAutoresizingFlexibleWidth;
 UIImageView *icon=[[UIImageView alloc]initWithImage:[UIImage imageWithContentsOfFile:[[NSBundle bundleForClass:owner.class] pathForResource:@"Icon" ofType:@"png"]]];icon.frame=CGRectMake((header.bounds.size.width-112)/2,14,112,112);icon.autoresizingMask=UIViewAutoresizingFlexibleLeftMargin|UIViewAutoresizingFlexibleRightMargin;icon.layer.cornerRadius=25;icon.clipsToBounds=YES;[header addSubview:icon];
 UILabel *title=[[UILabel alloc]initWithFrame:CGRectMake(12,140,header.bounds.size.width-24,32)];title.text=@"控制中心视频模块";title.font=[UIFont systemFontOfSize:23 weight:UIFontWeightBold];title.textAlignment=NSTextAlignmentCenter;title.autoresizingMask=UIViewAutoresizingFlexibleWidth;[header addSubview:title];
 UILabel *subtitle=[[UILabel alloc]initWithFrame:CGRectMake(12,178,header.bounds.size.width-24,24)];subtitle.text=@"Saoqiang · 3.1415926";subtitle.font=[UIFont systemFontOfSize:13];subtitle.textColor=UIColor.secondaryLabelColor;subtitle.textAlignment=NSTextAlignmentCenter;subtitle.autoresizingMask=UIViewAutoresizingFlexibleWidth;[header addSubview:subtitle];table.tableHeaderView=header;owner.view.tintColor=[UIColor colorWithRed:0.25 green:0.44 blue:0.95 alpha:1];
}
@implementation SQCCMPreferencesController
- (NSArray *)specifiers{
    if(!_specifiers){NSMutableArray *items=[NSMutableArray new];PSSpecifier *group=[PSSpecifier groupSpecifierWithName:@"控制中心视频模块 3.1415926"];[group setProperty:@"六个模块各自保存媒体、尺寸和不透明度；到设置→控制中心添加需要的编号。" forKey:@"footerText"];[items addObject:group];
        for(NSUInteger i=1;i<=6;++i){Class cls=NSClassFromString([NSString stringWithFormat:@"SQCCMModulePreferences%lu",(unsigned long)i]);PSSpecifier *row=[PSSpecifier preferenceSpecifierNamed:SQCCMDisplayName(i) target:self set:NULL get:NULL detail:cls cell:PSLinkCell edit:NULL];[items addObject:row];}_specifiers=items;
    }return _specifiers;
}
- (UITableViewStyle)tableViewStyle{return UITableViewStyleInsetGrouped;}
- (void)viewWillAppear:(BOOL)animated{[super viewWillAppear:animated];[self reloadSpecifiers];SQCCMDecorate(self);}
- (void)viewDidLoad{[super viewDidLoad];self.title=@"控制中心视频模块";SQCCMDecorate(self);}
@end

static BOOL SQCCMImportBusy=NO;
@implementation SQCCMModulePreferences
- (UITableViewStyle)tableViewStyle{return UITableViewStyleInsetGrouped;}
- (NSUInteger)sqccmModuleIndex{return 1;}
- (NSArray *)specifiers{
    if(!_specifiers){NSMutableArray *items=[[self loadSpecifiersFromPlistName:@"Root" target:self] mutableCopy];
        for(PSSpecifier *s in items){if([[s propertyForKey:@"key"] isEqual:@"opacity"])[s setProperty:SQCCMOpacityCell.class forKey:@"cellClass"];if([[s propertyForKey:@"key"] isEqual:@"cornerRadius"])[s setProperty:SQCCMCornerCell.class forKey:@"cellClass"];}
        _specifiers=items;
    }return _specifiers;
}
- (void)viewDidLoad{[super viewDidLoad];self.title=SQCCMDisplayName(self.sqccmModuleIndex);}
- (void)viewWillAppear:(BOOL)animated{[super viewWillAppear:animated];if(!self.presentedViewController)self.sqccmPicking=NO;self.title=SQCCMDisplayName(self.sqccmModuleIndex);[self reloadSpecifiers];SQCCMDecorate(self);}
- (void)presentationControllerDidDismiss:(UIPresentationController *)controller{self.sqccmPicking=NO;}
- (id)readPreferenceValue:(PSSpecifier *)specifier{
    NSDictionary *profile=SQCCMProfile(SQCCMRead(NULL),self.sqccmModuleIndex);NSString *key=[specifier propertyForKey:@"key"];
    if([key isEqual:@"width"]||[key isEqual:@"height"]){NSString *legacy=profile[@"moduleSize"]?:@"2x2";NSArray *parts=[legacy componentsSeparatedByString:@"x"];NSUInteger index=[key isEqual:@"width"]?0:1;id value=profile[key];return value?:@((parts.count==2?[parts[index] integerValue]:2));}
    return profile[key]?:[specifier propertyForKey:@"default"];
}
- (void)setPreferenceValue:(id)value specifier:(PSSpecifier *)specifier{[self sqccmStore:value key:[specifier propertyForKey:@"key"]];}
- (BOOL)sqccmStore:(id)value key:(NSString *)key{
    if([key isEqual:@"customName"]){if(![value isKindOfClass:NSString.class])return NO;value=[value stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];if([value length]>24)value=[value substringToIndex:24];}
    if(self.sqccmImporting){[self sqccmAlert:@"请等待当前模块导入完成。"];[self reloadSpecifiers];return NO;}
    if(!key||!value)return NO;
    if([key isEqual:@"moduleSize"]&&(![value isKindOfClass:NSString.class]||![SQCCMSizeKeys() containsObject:value]))return NO;
    if([key isEqual:@"cornerRadius"])value=@(MAX(0,MIN(60,[value doubleValue])));
    if([key isEqual:@"opacity"])value=@(SQCCMClampOpacity([value doubleValue]));
    if([@[@"width",@"height"] containsObject:key])value=@(MAX(1,MIN(4,lround([value doubleValue]))));
    NSError *error=nil;NSDictionary *root=SQCCMRead(&error);if(!root){[self sqccmAlert:error.localizedDescription];return NO;}
    NSMutableDictionary *profile=[SQCCMProfile(root,self.sqccmModuleIndex) mutableCopy];
    if([@[@"width",@"height"] containsObject:key]){NSString *legacy=profile[@"moduleSize"]?:@"2x2";NSArray *parts=[legacy componentsSeparatedByString:@"x"];NSInteger width=profile[@"width"]?[profile[@"width"] integerValue]:(parts.count==2?[parts[0] integerValue]:2);NSInteger height=profile[@"height"]?[profile[@"height"] integerValue]:(parts.count==2?[parts[1] integerValue]:2);if([key isEqual:@"width"])width=[value integerValue];else height=[value integerValue];profile[@"width"]=@(width);profile[@"height"]=@(height);profile[@"moduleSize"]=[NSString stringWithFormat:@"%ldx%ld",(long)width,(long)height];}
    else profile[key]=value;
    BOOL ok=SQCCMWrite(SQCCMReplacingProfile(root,self.sqccmModuleIndex,profile),&error);if(!ok)[self sqccmAlert:error.localizedDescription];
    if(ok && [@[@"width",@"height",@"moduleSize"] containsObject:key])CFNotificationCenterPostNotification(CFNotificationCenterGetDarwinNotifyCenter(),CFSTR("com.opa334.ccsupport/ReloadSizes"),NULL,NULL,YES);
    return ok;
}
- (void)sqccmOpacityChanged:(float)value{[self sqccmStore:@(value) key:@"opacity"];}
- (void)sqccmChooseSize{if(self.sqccmImporting||self.sqccmPicking)return;SQCCMSizePicker *page=[[SQCCMSizePicker alloc]initWithStyle:UITableViewStyleInsetGrouped];page.sqccmOwner=self;[self.navigationController pushViewController:page animated:YES];}
- (void)sqccmAlert:(NSString *)message{
    dispatch_async(dispatch_get_main_queue(),^{if(self.presentedViewController)return;UIAlertController *alert=[UIAlertController alertControllerWithTitle:SQCCMDisplayName(self.sqccmModuleIndex) message:message?:@"操作失败" preferredStyle:UIAlertControllerStyleAlert];[alert addAction:[UIAlertAction actionWithTitle:@"好" style:UIAlertActionStyleDefault handler:nil]];[self presentViewController:alert animated:YES completion:nil];});
}
- (void)sqccmChoosePhotos{
    if(SQCCMImportBusy||self.sqccmPicking){[self sqccmAlert:@"请等待当前导入完成。"];return;}
    PHPickerConfiguration *config=[PHPickerConfiguration new];config.selectionLimit=1;config.filter=[PHPickerFilter anyFilterMatchingSubfilters:@[PHPickerFilter.imagesFilter,PHPickerFilter.videosFilter]];config.preferredAssetRepresentationMode=PHPickerConfigurationAssetRepresentationModeCurrent;
    PHPickerViewController *picker=[[PHPickerViewController alloc]initWithConfiguration:config];picker.delegate=self;picker.modalPresentationStyle=UIModalPresentationFullScreen;self.sqccmPicking=YES;[self presentViewController:picker animated:YES completion:^{picker.presentationController.delegate=self;}];
}
- (void)sqccmChooseFiles{
    if(SQCCMImportBusy||self.sqccmPicking){[self sqccmAlert:@"请等待当前导入完成。"];return;}
    UIDocumentPickerViewController *picker=[[UIDocumentPickerViewController alloc]initForOpeningContentTypes:@[UTTypeImage,UTTypeMovie] asCopy:YES];picker.allowsMultipleSelection=NO;picker.delegate=self;picker.modalPresentationStyle=UIModalPresentationFullScreen;self.sqccmPicking=YES;[self presentViewController:picker animated:YES completion:^{picker.presentationController.delegate=self;}];
}
- (BOOL)sqccmBeginImport{
    if(SQCCMImportBusy)return NO;SQCCMImportBusy=YES;self.sqccmImporting=YES;self.sqccmPicking=NO;++self.sqccmImportGeneration;self.title=@"正在读取媒体…";return YES;
}
- (void)picker:(PHPickerViewController *)picker didFinishPicking:(NSArray<PHPickerResult *> *)results{
    [picker dismissViewControllerAnimated:YES completion:^{self.sqccmPicking=NO;NSItemProvider *provider=results.firstObject.itemProvider;if(!provider)return;if(![self sqccmBeginImport]){[self sqccmAlert:@"另一个模块正在导入，请稍后重试。"];return;}
        NSUInteger generation=self.sqccmImportGeneration;NSString *type=nil;BOOL video=[provider hasItemConformingToTypeIdentifier:UTTypeMovie.identifier];
        for(NSString *candidate in provider.registeredTypeIdentifiers){UTType *t=[UTType typeWithIdentifier:candidate];if([t conformsToType:video?UTTypeMovie:UTTypeImage]){type=candidate;break;}}
        if(!type)type=video?UTTypeMovie.identifier:UTTypeImage.identifier;
        self.sqccmProviderLoading=YES;
        self.sqccmProviderProgress=[provider loadFileRepresentationForTypeIdentifier:type completionHandler:^(NSURL *url,NSError *error){
            dispatch_async(dispatch_get_main_queue(),^{if(self.sqccmImportGeneration==generation)self.sqccmProviderLoading=NO;});
            // Copy before this callback returns; the provider may delete its URL.
            [self sqccmCopyProviderURL:url video:video type:type error:error generation:generation];
        }];
        __weak SQCCMModulePreferences *weakSelf=self;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,120*NSEC_PER_SEC),dispatch_get_main_queue(),^{
            SQCCMModulePreferences *owner=weakSelf;
            if(owner.sqccmProviderLoading&&owner.sqccmImporting&&owner.sqccmImportGeneration==generation){
                [owner.sqccmProviderProgress cancel];
                [owner sqccmFinishFile:nil temporary:nil video:video error:SQCCMError(31,@"相册读取超过120秒，请先将视频下载到本机再重试。") generation:generation];
            }
        });
    }];
}
- (void)documentPickerWasCancelled:(UIDocumentPickerViewController *)controller{(void)controller;self.sqccmPicking=NO;}
- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls{
    (void)controller;self.sqccmPicking=NO;NSURL *url=urls.firstObject;if(!url||![self sqccmBeginImport])return;NSUInteger generation=self.sqccmImportGeneration;
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{BOOL scoped=[url startAccessingSecurityScopedResource];UTType *type=nil;[url getResourceValue:&type forKey:NSURLContentTypeKey error:nil];if(!type)type=[UTType typeWithFilenameExtension:url.pathExtension];BOOL video=[type conformsToType:UTTypeMovie]||[@[@"mp4",@"mov",@"m4v"] containsObject:url.pathExtension.lowercaseString];[self sqccmCopyProviderURL:url video:video type:type.identifier error:nil generation:generation];if(scoped)[url stopAccessingSecurityScopedResource];});
}
- (void)sqccmCopyProviderURL:(NSURL *)url video:(BOOL)video type:(NSString *)type error:(NSError *)sourceError generation:(NSUInteger)generation{
    NSError *error=sourceError;NSFileManager *fm=NSFileManager.defaultManager;NSString *temporary=nil;
    if(!url&&!error)error=SQCCMError(20,@"选择器没有返回可读取的媒体文件。");
    NSNumber *size=nil;if(!error&&(![url getResourceValue:&size forKey:NSURLFileSizeKey error:&error]||!size||size.unsignedLongLongValue==0||size.unsignedLongLongValue>250ULL*1024*1024))if(!error)error=SQCCMError(21,@"媒体为空或超过250MB。");
    NSString *extension=url.pathExtension.lowercaseString;
    if(video&&![@[@"mov",@"mp4",@"m4v"] containsObject:extension]){UTType *container=[UTType typeWithIdentifier:type];NSString *candidate=container.preferredFilenameExtension;if([@[@"mov",@"mp4",@"m4v"] containsObject:candidate])extension=candidate;else extension=@"mov";}
    if(!video&&![extension length])extension=@"image";
    if(!error){NSURL *caches=[fm URLsForDirectory:NSCachesDirectory inDomains:NSUserDomainMask].firstObject;NSString *dir=[[caches URLByAppendingPathComponent:@"SaoqiangCCMedia-imports" isDirectory:YES] path];if(!dir||![fm createDirectoryAtPath:dir withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0700} error:&error]){if(!error)error=SQCCMError(22,@"无法创建媒体暂存目录。");}else{temporary=[dir stringByAppendingPathComponent:[NSString stringWithFormat:@"%@.%@",NSUUID.UUID.UUIDString,extension]];[fm copyItemAtURL:url toURL:[NSURL fileURLWithPath:temporary] error:&error];if(!error)[fm setAttributes:@{NSFilePosixPermissions:@0644} ofItemAtPath:temporary error:&error];}}
    if(error){dispatch_async(dispatch_get_main_queue(),^{[self sqccmFinishFile:nil temporary:temporary video:video error:error generation:generation];});return;}
    // All following work uses our owned copy; the picker URL can now disappear.
    dispatch_async(dispatch_get_main_queue(),^{
        if(generation!=self.sqccmImportGeneration){[fm removeItemAtPath:temporary error:nil];return;}
        self.sqccmTemporaryURL=[NSURL fileURLWithPath:temporary];
        if(video)[self sqccmValidateVideo:temporary generation:generation];
        else dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{
            NSError *saveError=nil;NSString *destination=nil;CGImageSourceRef source=CGImageSourceCreateWithURL((__bridge CFURLRef)[NSURL fileURLWithPath:temporary],NULL);
            CGImageRef image=source?CGImageSourceCreateThumbnailAtIndex(source,0,(__bridge CFDictionaryRef)@{(id)kCGImageSourceCreateThumbnailFromImageAlways:@YES,(id)kCGImageSourceCreateThumbnailWithTransform:@YES,(id)kCGImageSourceThumbnailMaxPixelSize:@2048,(id)kCGImageSourceShouldCacheImmediately:@YES}):NULL;
            if(image){if([fm createDirectoryAtPath:SQCCMMediaDirectory() withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0755} error:&saveError]){destination=[SQCCMMediaDirectory() stringByAppendingPathComponent:[NSString stringWithFormat:@"module%lu-%@.jpg",(unsigned long)self.sqccmModuleIndex,NSUUID.UUID.UUIDString]];CGImageDestinationRef output=CGImageDestinationCreateWithURL((__bridge CFURLRef)[NSURL fileURLWithPath:destination],(__bridge CFStringRef)UTTypeJPEG.identifier,1,NULL);BOOL ok=NO;if(output){CGImageDestinationAddImage(output,image,(__bridge CFDictionaryRef)@{(id)kCGImageDestinationLossyCompressionQuality:@0.9});ok=CGImageDestinationFinalize(output);CFRelease(output);}if(!ok)saveError=SQCCMError(23,@"图片保存失败。");}CGImageRelease(image);}else saveError=SQCCMError(24,@"无法解码所选图片。");if(source)CFRelease(source);
            dispatch_async(dispatch_get_main_queue(),^{[self sqccmFinishFile:destination temporary:temporary video:NO error:saveError generation:generation];});
        });
    });
}
- (void)sqccmValidateVideo:(NSString *)temporary generation:(NSUInteger)generation{
    NSError *error=nil;SQCCMPrefsVideoSource *reader=[[SQCCMPrefsVideoSource alloc]initWithPath:temporary error:&error];
    if(!reader){[self sqccmFinishFile:nil temporary:temporary video:YES error:error generation:generation];return;}
    self.sqccmValidating=YES;
    self.sqccmValidationSource=reader;self.sqccmValidationAsset=reader.asset;AVURLAsset *asset=reader.asset;
    [asset loadValuesAsynchronouslyForKeys:@[@"tracks",@"duration",@"playable"] completionHandler:^{
        NSError *failure=nil;
        for(NSString *key in @[@"tracks",@"duration",@"playable"]){NSError *underlying=nil;AVKeyValueStatus status=[asset statusOfValueForKey:key error:&underlying];if(status!=AVKeyValueStatusLoaded){failure=[NSError errorWithDomain:SQCCMDomain code:25 userInfo:@{NSLocalizedDescriptionKey:[NSString stringWithFormat:@"视频%@读取失败：%@（%@ %ld）",key,underlying.localizedDescription?:@"属性未加载",underlying.domain?:@"AVFoundation",(long)underlying.code],NSUnderlyingErrorKey:underlying?:SQCCMError(25,@"属性未加载")}];break;}}
        if(!failure&&![asset tracksWithMediaType:AVMediaTypeVideo].count)failure=SQCCMError(26,@"文件没有视频轨道，可能是 Live Photo 配套图片或损坏文件。");
        if(!failure&&!asset.playable)failure=SQCCMError(27,@"系统不支持播放这个视频编码，原媒体未替换。");
        double seconds=failure?0:CMTimeGetSeconds(asset.duration);
        if(!failure&&(!isfinite(seconds)||seconds<=0))failure=SQCCMError(28,@"视频时长无效。");
        if(!failure&&seconds>1200)failure=SQCCMError(29,@"视频超过20分钟，请选择短视频。");
        dispatch_async(dispatch_get_main_queue(),^{
            if(generation!=self.sqccmImportGeneration||!self.sqccmImporting)return;
            if(failure){[self sqccmFinishFile:nil temporary:temporary video:YES error:failure generation:generation];return;}
            self.sqccmValidating=NO;
            self.title=@"正在保存视频…";
            dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED,0),^{NSError *saveError=nil;NSString *destination=nil;NSFileManager *fm=NSFileManager.defaultManager;if([fm createDirectoryAtPath:SQCCMMediaDirectory() withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0755} error:&saveError]){destination=[SQCCMMediaDirectory() stringByAppendingPathComponent:[NSString stringWithFormat:@"module%lu-%@.%@",(unsigned long)self.sqccmModuleIndex,NSUUID.UUID.UUIDString,temporary.pathExtension]];[fm copyItemAtPath:temporary toPath:destination error:&saveError];}dispatch_async(dispatch_get_main_queue(),^{[self sqccmFinishFile:destination temporary:temporary video:YES error:saveError generation:generation];});});
        });
    }];
    __weak SQCCMModulePreferences *weakSelf=self;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,45*NSEC_PER_SEC),dispatch_get_main_queue(),^{SQCCMModulePreferences *owner=weakSelf;if(owner.sqccmValidating&&owner.sqccmValidationAsset==asset&&owner.sqccmImporting&&owner.sqccmImportGeneration==generation){[asset cancelLoading];[owner sqccmFinishFile:nil temporary:temporary video:YES error:SQCCMError(30,@"视频分析超过45秒，请使用本地下载完成的视频重试。") generation:generation];}});
}
- (void)sqccmFinishFile:(NSString *)file temporary:(NSString *)temporary video:(BOOL)video error:(NSError *)error generation:(NSUInteger)generation{
    NSCAssert(NSThread.isMainThread,@"Import finalization must be on the main queue");NSFileManager *fm=NSFileManager.defaultManager;
    if(generation!=self.sqccmImportGeneration||!self.sqccmImporting){if(file)[fm removeItemAtPath:file error:nil];if(temporary)[fm removeItemAtPath:temporary error:nil];return;}
    self.sqccmProviderLoading=NO;self.sqccmValidating=NO;[self.sqccmProviderProgress cancel];self.sqccmProviderProgress=nil;
    self.sqccmValidationAsset=nil;self.sqccmValidationSource=nil;self.sqccmTemporaryURL=nil;
    NSError *saveError=error;BOOL success=NO;
    if(!saveError&&file){[fm setAttributes:@{NSFilePosixPermissions:@0644} ofItemAtPath:file error:&saveError];NSDictionary *root=saveError?nil:SQCCMRead(&saveError);
        if(root){NSDictionary *old=SQCCMProfile(root,self.sqccmModuleIndex);NSMutableDictionary *profile=old.mutableCopy;profile[@"mediaName"]=file.lastPathComponent;profile[@"mediaKind"]=video?@"video":@"image";profile[@"enabled"]=@YES;[profile removeObjectForKey:@"widget"];NSDictionary *updated=SQCCMReplacingProfile(root,self.sqccmModuleIndex,profile);success=SQCCMWrite(updated,&saveError);if(success)SQCCMRemoveUnreferenced(SQCCMMediaPath(old),updated);}
    }
    if(!success&&file)[fm removeItemAtPath:file error:nil];if(temporary)[fm removeItemAtPath:temporary error:nil];self.sqccmImporting=NO;SQCCMImportBusy=NO;++self.sqccmImportGeneration;
    self.title=SQCCMDisplayName(self.sqccmModuleIndex);[self reloadSpecifiers];
    [self sqccmAlert:success?[NSString stringWithFormat:@"媒体已保存到模块 %lu。请打开本模块的启用开关，再到控制中心添加对应编号。",(unsigned long)self.sqccmModuleIndex]:[NSString stringWithFormat:@"%@\n%@ %ld",saveError.localizedDescription?:@"媒体导入失败，原配置保留",saveError.domain?:SQCCMDomain,(long)saveError.code]];
}
- (void)sqccmChooseWidget{
    if(SQCCMImportBusy||self.sqccmPicking||self.presentedViewController)return;
    UIAlertController *menu=[UIAlertController alertControllerWithTitle:@"选择小组件" message:@"内置时钟与日期；选择图片 / 视频可切回媒体。" preferredStyle:UIAlertControllerStyleActionSheet];
    NSArray *titles=@[@"数字时钟",@"日期日历",@"关闭小组件"];
    for(NSUInteger i=0;i<titles.count;i++){[menu addAction:[UIAlertAction actionWithTitle:titles[i] style:UIAlertActionStyleDefault handler:^(UIAlertAction *a){[self sqccmStore:@(i) key:@"widget"];[self sqccmStore:@YES key:@"enabled"];}]];}
    [menu addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];menu.popoverPresentationController.sourceView=self.view;menu.popoverPresentationController.sourceRect=CGRectMake(self.view.bounds.size.width/2,self.view.bounds.size.height/2,1,1);[self presentViewController:menu animated:YES completion:nil];
}
- (void)sqccmClearMedia{
    if(SQCCMImportBusy||self.sqccmPicking)return;NSUInteger index=self.sqccmModuleIndex;
    UIAlertController *alert=[UIAlertController alertControllerWithTitle:[NSString stringWithFormat:@"清除模块 %lu 的媒体？",(unsigned long)index] message:@"只删除本模块的导入副本，不影响其他模块或相册原件。" preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"取消" style:UIAlertActionStyleCancel handler:nil]];
    [alert addAction:[UIAlertAction actionWithTitle:@"清除" style:UIAlertActionStyleDestructive handler:^(UIAlertAction *action){(void)action;NSError *error=nil;NSDictionary *root=SQCCMRead(&error);if(!root){[self sqccmAlert:error.localizedDescription];return;}NSDictionary *old=SQCCMProfile(root,index);NSMutableDictionary *profile=old.mutableCopy;[profile removeObjectForKey:@"mediaName"];[profile removeObjectForKey:@"mediaKind"];NSDictionary *updated=SQCCMReplacingProfile(root,index,profile);if(SQCCMWrite(updated,&error))SQCCMRemoveUnreferenced(SQCCMMediaPath(old),updated);else [self sqccmAlert:error.localizedDescription];[self reloadSpecifiers];}]];
    [self presentViewController:alert animated:YES completion:nil];
}
@end
#define SQCCM_PREF_MODULE(N) \
@interface SQCCMModulePreferences##N : SQCCMModulePreferences @end \
@implementation SQCCMModulePreferences##N \
- (NSUInteger)sqccmModuleIndex{return N;} \
@end
SQCCM_PREF_MODULE(1)
SQCCM_PREF_MODULE(2)
SQCCM_PREF_MODULE(3)
SQCCM_PREF_MODULE(4)
SQCCM_PREF_MODULE(5)
SQCCM_PREF_MODULE(6)
