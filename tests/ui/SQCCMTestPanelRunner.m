#import <UIKit/UIKit.h>
#import <Preferences/PSListController.h>
#import <Preferences/PSSpecifier.h>
#import <Preferences/PSTableCell.h>
#import <objc/runtime.h>
#import "../../Shared/SQCCMStorage.h"

#ifndef SQCCM_TEST_RUN_TOKEN
#define SQCCM_TEST_RUN_TOKEN @"local"
#endif

@interface NSObject (SQCCMTestPanelAccess)
- (NSArray *)specifiers;
- (NSUInteger)sqccmModuleIndex;
- (id)readPreferenceValue:(PSSpecifier *)specifier;
- (void)setPreferenceValue:(id)value specifier:(PSSpecifier *)specifier;
- (BOOL)sqccmStore:(id)value key:(NSString *)key;
@end

@interface SQCCMTestApplicationDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) UINavigationController *navigationController;
@end

@interface SQCCMTestSuite : NSObject
@property(nonatomic, strong) NSMutableArray<NSString *> *failures;
@property(nonatomic) NSUInteger checks;
@property(nonatomic) NSUInteger completedCases;
@property(nonatomic, strong) PSListController *rootController;
@property(nonatomic, strong) NSMutableArray *moduleControllers;
@property(nonatomic, weak) SQCCMTestApplicationDelegate *appDelegate;
- (instancetype)initWithDelegate:(SQCCMTestApplicationDelegate *)delegate;
- (void)check:(BOOL)condition message:(NSString *)message;
- (void)runCase:(NSString *)name body:(void (^)(void))body;
- (BOOL)run;
@end

static void SQCCMTestCheck(SQCCMTestSuite *suite, BOOL condition, NSString *message) {
    suite.checks += 1;
    if (!condition) [suite.failures addObject:message ?: @"assertion failed"];
}

static PSSpecifier *SQCCMTestSpecifier(id controller, NSString *key) {
    for (PSSpecifier *specifier in [controller specifiers]) {
        if ([[specifier propertyForKey:@"key"] isEqual:key]) return specifier;
    }
    return nil;
}

static UILabel *SQCCMTestFindLabel(UIView *view, NSString *text) {
    if ([view isKindOfClass:UILabel.class] && [((UILabel *)view).text isEqual:text]) return (UILabel *)view;
    for (UIView *child in view.subviews) {
        UILabel *found = SQCCMTestFindLabel(child, text);
        if (found) return found;
    }
    return nil;
}

static UISlider *SQCCMTestFindSlider(UIView *view) {
    if ([view isKindOfClass:UISlider.class]) return (UISlider *)view;
    for (UIView *child in view.subviews) {
        UISlider *found = SQCCMTestFindSlider(child);
        if (found) return found;
    }
    return nil;
}

static BOOL SQCCMTestNear(double actual, double expected) {
    return fabs(actual - expected) < 0.015;
}

@implementation SQCCMTestSuite
- (instancetype)initWithDelegate:(SQCCMTestApplicationDelegate *)delegate {
    if ((self = [super init])) {
        _failures = [NSMutableArray array];
        _moduleControllers = [NSMutableArray array];
        _appDelegate = delegate;
        _rootController = delegate.navigationController.viewControllers.firstObject;
    }
    return self;
}
- (void)check:(BOOL)condition message:(NSString *)message {
    SQCCMTestCheck(self, condition, message);
}
- (void)runCase:(NSString *)name body:(void (^)(void))body {
    @try {
        body();
        self.completedCases += 1;
        NSLog(@"SQCCM_TEST_CASE_PASS %@", name);
    } @catch (NSException *exception) {
        [self.failures addObject:[NSString stringWithFormat:@"%@ raised %@: %@", name, exception.name, exception.reason ?: @""]];
        NSLog(@"SQCCM_TEST_CASE_FAIL %@ %@", name, exception);
    }
}
- (NSDictionary *)readConfig {
    NSError *error = nil;
    NSDictionary *root = SQCCMRead(&error);
    [self check:root != nil && error == nil message:[NSString stringWithFormat:@"config read failed: %@", error]];
    return root ?: @{};
}
- (BOOL)writeConfig:(NSDictionary *)config {
    NSError *error = nil;
    BOOL ok = SQCCMWrite(config, &error);
    [self check:ok message:[NSString stringWithFormat:@"config write failed: %@", error]];
    return ok;
}
- (void)setValue:(id)value key:(NSString *)key on:(id)controller {
    PSSpecifier *specifier = SQCCMTestSpecifier(controller, key);
    [self check:specifier != nil message:[NSString stringWithFormat:@"missing specifier %@", key]];
    if (specifier) [controller setPreferenceValue:value specifier:specifier];
}
- (id)valueForKey:(NSString *)key on:(id)controller {
    PSSpecifier *specifier = SQCCMTestSpecifier(controller, key);
    [self check:specifier != nil message:[NSString stringWithFormat:@"missing specifier %@", key]];
    return specifier ? [controller readPreferenceValue:specifier] : nil;
}
- (BOOL)run {
    NSString *sandbox = [NSHomeDirectory() stringByAppendingPathComponent:@"SQCCMTestRoot"];
    NSString *configPath = SQCCMConfigPath();
    [self check:[configPath hasPrefix:[sandbox stringByAppendingString:@"/"]] message:@"ROOTHIDE config path escaped the simulator app sandbox"];
    NSError *cleanupError = nil;
    [[NSFileManager defaultManager] removeItemAtPath:configPath error:&cleanupError];
    [self check:cleanupError == nil || cleanupError.code == NSFileNoSuchFileError message:@"could not clear isolated test config"];

    [self runCase:@"root-load-title-retention-and-detail-map" body:^{
        [self.rootController loadViewIfNeeded];
        [self check:[self.rootController isViewLoaded] message:@"root viewDidLoad was not reached"];
        [self check:[self.rootController.title isEqual:@"控制中心视频模块"] message:@"root navigation title is wrong"];
        NSString *retainedTitle = [self.rootController.title copy];
        [[NSRunLoop mainRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.04]];
        [self check:[self.rootController.title isEqual:retainedTitle] message:@"root title did not remain retained/copied"];
        NSArray *specifiers = [self.rootController specifiers];
        [self check:specifiers.count == 7 message:@"root must contain one group and six module rows"];
        PSSpecifier *first = specifiers.firstObject;
        [self check:[first.name isEqual:@"控制中心视频模块 3.1415926"] message:@"first root heading was lost"];
        UITableView *table = ((UIViewController *)self.rootController).view.subviews.firstObject;
        (void)table;
        UIView *header = ((UITableViewController *)self.rootController).tableView.tableHeaderView;
        [self check:SQCCMTestFindLabel(header, @"控制中心视频模块") != nil message:@"decorated header title not retained"];
        for (NSUInteger i = 1; i <= 6; i++) {
            PSSpecifier *row = specifiers[i];
            NSString *expectedName = [NSString stringWithFormat:@"视频模块 %lu", (unsigned long)i];
            NSString *className = [NSString stringWithFormat:@"SQCCMModulePreferences%lu", (unsigned long)i];
            [self check:[row.name isEqual:expectedName] message:[NSString stringWithFormat:@"wrong detail row title for module %lu", (unsigned long)i]];
            [self check:row.detail == NSClassFromString(className) message:[NSString stringWithFormat:@"wrong detail mapping for %@", className]];
            [self check:row.target == self.rootController message:[NSString stringWithFormat:@"row %@ has wrong target", className]];
            if (i == 1 && row.detail) {
                UIViewController *detail = [[row.detail alloc] initWithStyle:UITableViewStyleInsetGrouped];
                [self.appDelegate.navigationController pushViewController:detail animated:NO];
                [detail loadViewIfNeeded];
                [self check:self.appDelegate.navigationController.topViewController == detail message:@"root detail row failed real UIKit push"];
                [self check:[[detail specifiers] count] > 15 message:@"pushed detail did not invoke Root.plist specifier loader"];
                [self.appDelegate.navigationController popViewControllerAnimated:NO];
                [self check:self.appDelegate.navigationController.topViewController == self.rootController message:@"real detail pop did not restore root"];
            }
        }
    }];

    [self runCase:@"six-module-init-and-real-root-plist-load" body:^{
        NSUInteger expectedCount = 0;
        for (NSUInteger i = 1; i <= 6; i++) {
            NSString *className = [NSString stringWithFormat:@"SQCCMModulePreferences%lu", (unsigned long)i];
            Class moduleClass = NSClassFromString(className);
            [self check:moduleClass != Nil message:[NSString stringWithFormat:@"missing class %@", className]];
            if (!moduleClass) continue;
            id controller = [[moduleClass alloc] initWithStyle:UITableViewStyleInsetGrouped];
            [controller loadViewIfNeeded];
            [self check:[controller isViewLoaded] message:[NSString stringWithFormat:@"%@ did not load UIKit view", className]];
            [self check:[[controller specifiers] count] > 15 message:[NSString stringWithFormat:@"%@ did not load bundled Root.plist", className]];
            [self check:[[controller specifiers] count] == [[self.moduleControllers.firstObject specifiers] count] || self.moduleControllers.count == 0 message:@"module Root.plist row counts differ"];
            [self check:[[controller valueForKey:@"title"] isEqual:[NSString stringWithFormat:@"视频模块 %lu", (unsigned long)i]] message:[NSString stringWithFormat:@"%@ title not initialized", className]];
            [self check:[[controller valueForKey:@"sqccmModuleIndex"] unsignedIntegerValue] == i message:[NSString stringWithFormat:@"%@ index mismatch", className]];
            [self.moduleControllers addObject:controller];
        }
        expectedCount = self.moduleControllers.count;
        [self check:expectedCount == 6 message:@"did not initialize all six module controllers"];
    }];

    [self runCase:@"default-value-reads-and-bundled-specifiers" body:^{
        id module = self.moduleControllers.firstObject;
        NSDictionary *defaults = @{@"enabled": @NO, @"customName": @"", @"opacity": @1.0, @"cornerRadius": @22,
                                   @"width": @2, @"height": @2, @"contentMode": @1, @"noMargin": @NO,
                                   @"pixelArt": @NO, @"sound": @NO, @"deviceStyle": @NO};
        for (NSString *key in defaults) {
            id actual = [self valueForKey:key on:module];
            [self check:[actual isEqual:defaults[key]] message:[NSString stringWithFormat:@"default read mismatch for %@: %@", key, actual]];
        }
        NSBundle *bundle = NSBundle.mainBundle;
        [self check:[bundle pathForResource:@"Root" ofType:@"plist"] != nil message:@"original Root.plist not bundled"];
        for (NSString *png in @[@"Icon", @"ListIcon", @"ListIcon@2x", @"ListIcon@3x"]) {
            [self check:[bundle pathForResource:png ofType:@"png"] != nil message:[NSString stringWithFormat:@"original %@.png not bundled", png]];
        }
    }];

    [self runCase:@"per-module-isolation-and-persistent-reread" body:^{
        id first = self.moduleControllers[0], second = self.moduleControllers[1];
        [self setValue:@0.3 key:@"opacity" on:first];
        [self setValue:@0.7 key:@"opacity" on:second];
        [self setValue:@"Panel Two" key:@"customName" on:second];
        NSDictionary *diskRead = [self readConfig];
        NSDictionary *one = SQCCMProfile(diskRead, 1), *two = SQCCMProfile(diskRead, 2);
        [self check:SQCCMTestNear([one[@"opacity"] doubleValue], 0.3) message:@"module 1 opacity did not persist"];
        [self check:SQCCMTestNear([two[@"opacity"] doubleValue], 0.7) message:@"module 2 opacity did not persist"];
        [self check:[two[@"customName"] isEqual:@"Panel Two"] message:@"module 2 custom name did not persist"];
        [self check:one[@"customName"] == nil message:@"module 2 name leaked into module 1"];
        [self check:[diskRead[@"schemaVersion"] isEqual:@2] message:@"schema version not upgraded on write"];
        PSListController *reloaded = [[NSClassFromString(@"SQCCMModulePreferences2") alloc] initWithStyle:UITableViewStyleInsetGrouped];
        [reloaded loadViewIfNeeded];
        [self check:[reloaded.title isEqual:@"Panel Two"] message:@"saved title not restored on controller re-entry"];
        [self check:SQCCMTestNear([[reloaded readPreferenceValue:SQCCMTestSpecifier(reloaded, @"opacity")] doubleValue], 0.7) message:@"disk value not read by fresh controller"];
    }];

    [self runCase:@"legacy-size-and-size-clamps" body:^{
        NSDictionary *root = [self readConfig];
        NSDictionary *legacyRoot = SQCCMReplacingProfile(root, 3, @{@"moduleSize": @"3x4"});
        [self writeConfig:legacyRoot];
        id legacy = self.moduleControllers[2];
        [self check:[[self valueForKey:@"width" on:legacy] integerValue] == 3 message:@"legacy moduleSize width was not read"];
        [self check:[[self valueForKey:@"height" on:legacy] integerValue] == 4 message:@"legacy moduleSize height was not read"];
        id sizeOwner = self.moduleControllers[3];
        [self setValue:@(-50) key:@"width" on:sizeOwner];
        [self setValue:@(99) key:@"height" on:sizeOwner];
        NSDictionary *saved = SQCCMProfile([self readConfig], 4);
        [self check:[saved[@"width"] integerValue] == 1 message:@"width did not clamp to 1"];
        [self check:[saved[@"height"] integerValue] == 4 message:@"height did not clamp to 4"];
        [self check:[saved[@"moduleSize"] isEqual:@"1x4"] message:@"legacy moduleSize was not kept in sync"];
        [self setValue:@(2.6) key:@"width" on:sizeOwner];
        [self check:[[self valueForKey:@"width" on:sizeOwner] integerValue] == 3 message:@"fractional width was not rounded"];
    }];

    [self runCase:@"opacity-and-corner-clamps" body:^{
        id module = self.moduleControllers[0];
        [self setValue:@(-2.0) key:@"opacity" on:module];
        [self check:SQCCMTestNear([[self valueForKey:@"opacity" on:module] doubleValue], 0) message:@"opacity lower clamp failed"];
        [self setValue:@(2.5) key:@"opacity" on:module];
        [self check:SQCCMTestNear([[self valueForKey:@"opacity" on:module] doubleValue], 1) message:@"opacity upper clamp failed"];
        [self setValue:@(-10) key:@"cornerRadius" on:module];
        [self check:[[self valueForKey:@"cornerRadius" on:module] integerValue] == 0 message:@"corner radius lower clamp failed"];
        [self setValue:@(120) key:@"cornerRadius" on:module];
        [self check:[[self valueForKey:@"cornerRadius" on:module] integerValue] == 60 message:@"corner radius upper clamp failed"];
    }];

    [self runCase:@"custom-slider-refresh-and-prepare-for-reuse" body:^{
        id first = self.moduleControllers[0], second = self.moduleControllers[1];
        [self setValue:@0.63 key:@"opacity" on:first]; [self setValue:@31 key:@"cornerRadius" on:first];
        [self setValue:@0.28 key:@"opacity" on:second]; [self setValue:@12 key:@"cornerRadius" on:second];
        Class opacityClass = NSClassFromString(@"SQCCMOpacityCell");
        Class cornerClass = NSClassFromString(@"SQCCMCornerCell");
        PSSpecifier *opacitySpecifier = SQCCMTestSpecifier(first, @"opacity");
        PSSpecifier *cornerSpecifier = SQCCMTestSpecifier(first, @"cornerRadius");
        [self check:opacityClass && cornerClass message:@"custom slider cell classes missing"];
        id opacityCell = [[opacityClass alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:@"opacity" specifier:opacitySpecifier];
        UISlider *opacitySlider = SQCCMTestFindSlider(opacityCell);
        [self check:opacitySlider != nil && SQCCMTestNear(opacitySlider.value, 0.63) message:@"opacity cell failed to refresh slider value"];
        [self check:SQCCMTestFindLabel(opacityCell, @"63%") != nil message:@"opacity cell failed to refresh percentage label"];
        [opacityCell prepareForReuse];
        [self check:[opacityCell valueForKey:@"sqccmOwner"] == nil message:@"opacity cell retained owner after reuse"];
        opacitySpecifier.target = second;
        [opacityCell refreshCellContentsWithSpecifier:opacitySpecifier];
        [self check:SQCCMTestNear(opacitySlider.value, 0.28) message:@"opacity cell refresh kept previous module value"];
        opacitySlider.value = 0.44;
        [opacitySlider sendActionsForControlEvents:UIControlEventTouchUpInside];
        [self check:SQCCMTestNear([SQCCMProfile([self readConfig], 2)[@"opacity"] doubleValue], 0.44) message:@"opacity slider commit did not persist"];

        id cornerCell = [[cornerClass alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:@"corner" specifier:cornerSpecifier];
        UISlider *cornerSlider = SQCCMTestFindSlider(cornerCell);
        [self check:cornerSlider != nil && SQCCMTestNear(cornerSlider.value, 31) message:@"corner cell failed to refresh slider value"];
        [self check:SQCCMTestFindLabel(cornerCell, @"31 pt") != nil message:@"corner cell failed to refresh point label"];
        [cornerCell prepareForReuse];
        [self check:[cornerCell valueForKey:@"sqccmOwner"] == nil message:@"corner cell retained owner after reuse"];
        cornerSpecifier.target = second;
        [cornerCell refreshCellContentsWithSpecifier:cornerSpecifier];
        [self check:SQCCMTestNear(cornerSlider.value, 12) message:@"corner cell refresh kept previous module value"];
        cornerSlider.value = 40;
        [cornerSlider sendActionsForControlEvents:UIControlEventTouchUpInside];
        [self check:[[SQCCMProfile([self readConfig], 2)[@"cornerRadius"] description] isEqual:@"40"] message:@"corner slider commit did not persist"];
    }];

    [self runCase:@"reversible-panel-exit-and-reentry" body:^{
        UINavigationController *navigation = self.appDelegate.navigationController;
        Class moduleClass = NSClassFromString(@"SQCCMModulePreferences6");
        PSListController *before = [[moduleClass alloc] initWithStyle:UITableViewStyleInsetGrouped];
        [self setValue:@0.51 key:@"opacity" on:before];
        [navigation pushViewController:before animated:NO];
        [before loadViewIfNeeded];
        [self check:navigation.topViewController == before message:@"detail panel did not enter navigation stack"];
        [self check:[before.title isEqual:@"视频模块 6"] message:@"detail title wrong on entry"];
        [navigation popViewControllerAnimated:NO];
        [self check:navigation.topViewController == self.rootController message:@"detail panel did not exit back to root"];
        id after = [[moduleClass alloc] initWithStyle:UITableViewStyleInsetGrouped];
        [navigation pushViewController:after animated:NO];
        [after loadViewIfNeeded];
        [self check:after != before message:@"re-entry reused old panel instance"];
        [self check:navigation.topViewController == after message:@"new detail panel did not re-enter"];
        [self check:SQCCMTestNear([[self valueForKey:@"opacity" on:after] doubleValue], 0.51) message:@"saved configuration lost on exit/re-entry"];
        [navigation popViewControllerAnimated:NO];
        [self check:navigation.topViewController == self.rootController message:@"second panel exit did not restore root"];
    }];
    return self.failures.count == 0 && self.checks > 0 && self.completedCases > 0;
}
@end

@implementation SQCCMTestApplicationDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    (void)application; (void)options;
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    Class rootClass = NSClassFromString(@"SQCCMPreferencesController");
    id root = [[rootClass alloc] initWithStyle:UITableViewStyleInsetGrouped];
    self.navigationController = [[UINavigationController alloc] initWithRootViewController:root];
    self.window.rootViewController = self.navigationController;
    [self.window makeKeyAndVisible];
    dispatch_async(dispatch_get_main_queue(), ^{
        SQCCMTestSuite *suite = [[SQCCMTestSuite alloc] initWithDelegate:self];
        BOOL passed = [suite run];
        NSString *documents = [NSHomeDirectory() stringByAppendingPathComponent:@"Documents"];
        [[NSFileManager defaultManager] createDirectoryAtPath:documents withIntermediateDirectories:YES attributes:nil error:nil];
        NSDictionary *result = @{@"runToken": SQCCM_TEST_RUN_TOKEN,
                                 @"status": passed ? @"PASS" : @"FAIL",
                                 @"mode": @"real-uikit-public-frameworks-test-only-preferences-substitute",
                                 @"checks": @(suite.checks),
                                 @"completedCases": @(suite.completedCases),
                                 @"failures": [suite.failures copy]};
        NSString *path = [documents stringByAppendingPathComponent:@"sqccm-uikit-result.json"];
        NSData *data = [NSJSONSerialization dataWithJSONObject:result options:NSJSONWritingPrettyPrinted error:nil];
        BOOL wrote = data && [data writeToFile:path options:NSDataWritingAtomic error:nil];
        NSLog(@"SQCCM_TEST_RESULT %@", result);
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.5 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
            exit(passed && wrote ? 0 : 1);
        });
    });
    return YES;
}
@end

int main(int argc, char *argv[]) {
    @autoreleasepool {
        return UIApplicationMain(argc, argv, nil, NSStringFromClass(SQCCMTestApplicationDelegate.class));
    }
}
