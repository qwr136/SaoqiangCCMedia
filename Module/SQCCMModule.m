#import <UIKit/UIKit.h>
#import <AVFoundation/AVFoundation.h>
#import <ImageIO/ImageIO.h>
#import <ControlCenterUIKit/CCUIContentModule-Protocol.h>
#import "../Shared/SQCCMStorage.h"
#ifndef SQCCM_MODULE_INDEX
#define SQCCM_MODULE_INDEX 1
#endif
#define SQCCM_JOIN_(A,B) A##B
#define SQCCM_JOIN(A,B) SQCCM_JOIN_(A,B)
#define SQCCMContentViewController SQCCM_JOIN(SQCCMMediaController,SQCCM_MODULE_INDEX)
#define SQCCMModule SQCCM_JOIN(SQCCMMediaModule,SQCCM_MODULE_INDEX)
#define SQCCM_VIDEO_SOURCE_CLASS SQCCM_JOIN(SQCCMMediaVideoSource,SQCCM_MODULE_INDEX)
#import "../Shared/SQCCMVideoSource.h"
typedef struct { NSUInteger width,height; } SQCCMLayoutSize;
static char SQCCMPlayerContext, SQCCMItemContext, SQCCMLooperContext;


@interface SQCCMContentViewController : UIViewController <CCUIContentModuleContentViewController>
@property(nonatomic,strong) UIViewController *sqccmPreviewController;
@property(nonatomic,strong) NSTimer *sqccmClock;
@property(nonatomic,strong) UIButton *sqccmClose;
@property(nonatomic,strong) UILabel *sqccmCaption;
@property(nonatomic,strong) UIImageView *sqccmImage;
@property(nonatomic,strong) UILabel *sqccmLabel;
@property(nonatomic,strong) UIButton *sqccmButton;
@property(nonatomic,strong) AVQueuePlayer *sqccmPlayer;
@property(nonatomic,strong) AVPlayerLooper *sqccmLooper;
@property(nonatomic,strong) AVPlayerLayer *sqccmLayer;
@property(nonatomic,strong) SQCCM_VIDEO_SOURCE_CLASS *sqccmVideoSource;
@property(nonatomic,strong) AVPlayerItem *sqccmObservedItem;
@property(nonatomic) BOOL sqccmObservingPlayer;
@property(nonatomic) BOOL sqccmObservingLooper;
@property(nonatomic) BOOL sqccmPlaybackFailed;
@property(nonatomic,copy) NSDictionary *sqccmConfig;
@property(nonatomic,copy) NSString *sqccmLoadedPath;
@property(nonatomic) BOOL sqccmVisible;
@property(nonatomic) BOOL sqccmExpanded;
@property(nonatomic) BOOL sqccmUserPaused;
@property(nonatomic) BOOL sqccmUserRequestedPlay;
@property(nonatomic) BOOL sqccmSuspended;
@property(nonatomic) BOOL sqccmClosing;
@property(nonatomic) BOOL sqccmNeedsRestart;
@property(nonatomic) BOOL sqccmSeekingStart;
@property(nonatomic) NSUInteger sqccmPresentationToken;
- (void)sqccmRestartIfNeeded;
@property(nonatomic) NSUInteger sqccmGeneration;
@property(nonatomic,strong) NSTimer *sqccmWatchdog;
@property(nonatomic) double sqccmLastTime;
@property(nonatomic) CFTimeInterval sqccmLastProgress;
@property(nonatomic) NSInteger sqccmRecoveryStep;
@property(nonatomic) NSInteger sqccmRebuildCount;
- (void)sqccmUpdatePlayback;
- (void)sqccmWatchPlayback;

- (void)sqccmReload;
@end
static void SQCCMConfigurationChanged(CFNotificationCenterRef center, void *observer, CFStringRef name, const void *object, CFDictionaryRef info) {
    SQCCMContentViewController *controller = (__bridge SQCCMContentViewController *)observer;
    dispatch_async(dispatch_get_main_queue(), ^{ [controller sqccmReload]; });
}
@implementation SQCCMContentViewController
- (instancetype)init {
    if ((self = [super init])) {
        CFNotificationCenterAddObserver(CFNotificationCenterGetDarwinNotifyCenter(), (__bridge const void *)self, SQCCMConfigurationChanged, (__bridge CFStringRef)SQCCMChanged, NULL, CFNotificationSuspensionBehaviorDeliverImmediately);
        [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(sqccmResign:) name:UIApplicationWillResignActiveNotification object:nil];
        [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(sqccmFailedToEnd:) name:AVPlayerItemFailedToPlayToEndTimeNotification object:nil];
    }
    return self;
}
- (void)dealloc {
    CFNotificationCenterRemoveEveryObserver(CFNotificationCenterGetDarwinNotifyCenter(), (__bridge const void *)self);
    [NSNotificationCenter.defaultCenter removeObserver:self];
    [self.sqccmClock invalidate];[self.sqccmWatchdog invalidate];[self sqccmClear];
}
- (void)loadView {
    self.view = [UIView new]; self.view.backgroundColor = UIColor.clearColor;
    self.view.clipsToBounds = YES;
    self.sqccmImage = [UIImageView new]; self.sqccmImage.contentMode = UIViewContentModeScaleAspectFit;
    self.sqccmImage.clipsToBounds = YES; [self.view addSubview:self.sqccmImage];
    self.sqccmLabel = [UILabel new]; self.sqccmLabel.numberOfLines = 0;
    self.sqccmLabel.textColor = UIColor.whiteColor; self.sqccmLabel.textAlignment = NSTextAlignmentCenter;
    self.sqccmLabel.font = [UIFont systemFontOfSize:13 weight:UIFontWeightMedium];
    [self.view addSubview:self.sqccmLabel];
    self.sqccmClose=[UIButton buttonWithType:UIButtonTypeSystem];[self.sqccmClose setTitle:@"返回" forState:UIControlStateNormal];self.sqccmClose.tintColor=UIColor.whiteColor;self.sqccmClose.backgroundColor=[UIColor colorWithWhite:0 alpha:0.6];self.sqccmClose.layer.cornerRadius=12;[self.sqccmClose addTarget:self action:@selector(sqccmCollapse) forControlEvents:UIControlEventTouchUpInside];[self.view addSubview:self.sqccmClose];
    self.sqccmCaption=[UILabel new];self.sqccmCaption.textColor=UIColor.whiteColor;self.sqccmCaption.textAlignment=NSTextAlignmentCenter;self.sqccmCaption.font=[UIFont systemFontOfSize:12];[self.view addSubview:self.sqccmCaption];UITapGestureRecognizer *tap=[[UITapGestureRecognizer alloc]initWithTarget:self action:@selector(sqccmPreview:)];[self.sqccmImage addGestureRecognizer:tap];self.sqccmImage.userInteractionEnabled=YES;[self sqccmReload];
}
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];if(self.sqccmPreviewController)return;CGRect media=SQCCMBool(self.sqccmConfig,@"noMargin",NO)?self.view.bounds:CGRectInset(self.view.bounds,4,4);self.sqccmImage.frame=media;self.sqccmLayer.frame=media;
    if(self.sqccmPreviewController)return;self.sqccmClose.hidden=YES;self.sqccmClose.frame=CGRectMake(8,8,60,30);self.sqccmCaption.frame=CGRectMake(8,MAX(0,self.view.bounds.size.height-24),MAX(0,self.view.bounds.size.width-16),20);
    self.sqccmLabel.frame = CGRectInset(self.view.bounds, 8, 8);
    self.sqccmButton.frame = CGRectMake(MAX(4, self.view.bounds.size.width-48), MAX(4, self.view.bounds.size.height-38), 40, 30);
}
- (void)sqccmCollapse {
    UIViewController *preview=self.sqccmPreviewController;if(!preview)return;
    // Restore the existing decoded image / player layer without creating a second decoder.
    self.sqccmImage.userInteractionEnabled=YES;[self.view insertSubview:self.sqccmImage atIndex:0];
    if(self.sqccmLayer){[self.sqccmLayer removeFromSuperlayer];[self.view.layer insertSublayer:self.sqccmLayer atIndex:0];}
    [self.sqccmClose removeFromSuperview];[self.view addSubview:self.sqccmClose];self.sqccmClose.hidden=YES;
    [preview dismissViewControllerAnimated:NO completion:^{self.sqccmPreviewController=nil;[self.view setNeedsLayout];[self.view layoutIfNeeded];[self sqccmUpdatePlayback];}];
}
- (void)sqccmPreviewTapped:(UITapGestureRecognizer *)gesture {if(gesture.state==UIGestureRecognizerStateEnded)[self sqccmCollapse];}
- (void)sqccmPreview:(UITapGestureRecognizer *)gesture {
    if(self.sqccmPreviewController)return;
    if(self.presentedViewController||!self.view.window)return;
    self.sqccmVisible=YES;self.sqccmSuspended=NO;self.sqccmLastProgress=CACurrentMediaTime();[self sqccmUpdatePlayback];
    UIViewController *preview=[UIViewController new];preview.modalPresentationStyle=UIModalPresentationOverFullScreen;preview.view.backgroundColor=UIColor.blackColor;self.sqccmPreviewController=preview;
    UITapGestureRecognizer *dismissTap=[[UITapGestureRecognizer alloc]initWithTarget:self action:@selector(sqccmPreviewTapped:)];[preview.view addGestureRecognizer:dismissTap];
    self.sqccmImage.userInteractionEnabled=NO;[preview.view addSubview:self.sqccmImage];self.sqccmImage.frame=preview.view.bounds;self.sqccmImage.autoresizingMask=UIViewAutoresizingFlexibleWidth|UIViewAutoresizingFlexibleHeight;
    if(self.sqccmLayer){[self.sqccmLayer removeFromSuperlayer];[preview.view.layer insertSublayer:self.sqccmLayer atIndex:0];self.sqccmLayer.frame=preview.view.bounds;}
    [preview.view addSubview:self.sqccmClose];self.sqccmClose.hidden=YES;self.sqccmClose.frame=CGRectMake(16,60,64,36);
    [self presentViewController:preview animated:NO completion:^{self.sqccmImage.frame=preview.view.bounds;self.sqccmLayer.frame=preview.view.bounds;[self sqccmUpdatePlayback];}];
}
- (CGFloat)preferredExpandedContentHeight { return 300; }
- (CGFloat)preferredExpandedContentWidth { return 330; }
- (BOOL)providesOwnPlatter { return YES; }
- (BOOL)shouldBeginTransitionToExpandedContentModule { return NO; }
- (BOOL)shouldFinishTransitionToExpandedContentModule { return NO; }
- (void)willTransitionToExpandedContentMode:(BOOL)expanded { self.sqccmExpanded = expanded; }
- (void)didTransitionToExpandedContentMode:(BOOL)expanded {
    self.sqccmExpanded = expanded; [self sqccmUpdatePlayback]; [self.view setNeedsLayout];
}
- (void)controlCenterWillPresent {
    if(!self.sqccmVisible||self.sqccmClosing||self.sqccmSuspended){self.sqccmNeedsRestart=YES;self.sqccmSeekingStart=NO;self.sqccmPresentationToken++;}
    self.sqccmClosing=NO;
    self.sqccmLastProgress=CACurrentMediaTime();self.sqccmRebuildCount=0;self.sqccmRecoveryStep=0;self.sqccmVisible = YES; self.sqccmUserPaused = NO; self.sqccmUserRequestedPlay = NO; self.sqccmSuspended = NO;
    [self loadViewIfNeeded]; [self sqccmReload];
}
- (void)sqccmSilence { self.sqccmPresentationToken++;self.sqccmSeekingStart=NO;self.sqccmNeedsRestart=YES; [self.sqccmWatchdog invalidate];self.sqccmWatchdog=nil;self.sqccmSuspended=YES;self.sqccmVisible=NO;self.sqccmPlayer.muted=YES;self.sqccmPlayer.volume=0;[self.sqccmPlayer pause]; }
- (void)controlCenterWillDismiss { self.sqccmClosing=YES;[self sqccmSilence]; }
- (void)willResignActive { self.sqccmClosing=YES;[self sqccmSilence]; }
- (void)willBecomeActive { if(!self.sqccmVisible||self.sqccmClosing||self.sqccmSuspended){self.sqccmNeedsRestart=YES;self.sqccmSeekingStart=NO;self.sqccmPresentationToken++;}self.sqccmClosing=NO;self.sqccmSuspended=NO;self.sqccmVisible=YES;[self sqccmUpdatePlayback]; }
- (void)viewWillDisappear:(BOOL)animated { [super viewWillDisappear:animated];
    if(!self.sqccmPreviewController){self.sqccmClosing=YES;[self sqccmSilence];
        __weak typeof(self) weakSelf=self;
        [self.transitionCoordinator animateAlongsideTransition:nil completion:^(id<UIViewControllerTransitionCoordinatorContext> context){
            typeof(self) owner=weakSelf;if(owner&&context.isCancelled){owner.sqccmClosing=NO;owner.sqccmVisible=YES;owner.sqccmSuspended=NO;[owner sqccmUpdatePlayback];}
        }];
    }
}
- (void)controlCenterDidDismiss { if(!self.sqccmClosing)return;[self sqccmSilence]; self.sqccmVisible = NO; [self.sqccmPlayer pause]; [self sqccmUpdatePlayback]; }
- (void)displayWillTurnOff { [self sqccmSilence]; self.sqccmVisible = NO; [self.sqccmPlayer pause]; [self sqccmUpdatePlayback]; }
- (void)sqccmResign:(NSNotification *)notification { [self sqccmSilence]; self.sqccmVisible = NO; self.sqccmSuspended = YES; [self sqccmUpdatePlayback]; }
- (void)viewDidDisappear:(BOOL)animated { [super viewDidDisappear:animated];
    if(self.sqccmPreviewController){[self sqccmUpdatePlayback];return;}
    if(self.sqccmClosing)[self sqccmSilence];[self.sqccmClock invalidate];self.sqccmClock=nil;
}
- (void)viewWillAppear:(BOOL)animated { [super viewWillAppear:animated];if(!self.sqccmPreviewController&&(!self.sqccmVisible||self.sqccmClosing||self.sqccmSuspended)){self.sqccmNeedsRestart=YES;self.sqccmSeekingStart=NO;self.sqccmPresentationToken++;}self.sqccmClosing=NO;self.sqccmVisible=YES;self.sqccmSuspended=NO;self.sqccmLastProgress=CACurrentMediaTime();[self sqccmReload]; }
- (void)viewDidAppear:(BOOL)animated { [super viewDidAppear:animated];self.sqccmClosing=NO;self.sqccmVisible=YES;self.sqccmSuspended=NO;[self sqccmUpdatePlayback]; }
- (BOOL)canDismissPresentedContent { return YES; }
- (void)dismissPresentedContentAnimated:(BOOL)animated completion:(id)completion {
    if(self.sqccmPreviewController){
        UIViewController *preview=self.sqccmPreviewController;
        self.sqccmImage.userInteractionEnabled=YES;[self.view insertSubview:self.sqccmImage atIndex:0];
        [self.sqccmLayer removeFromSuperlayer];if(self.sqccmLayer)[self.view.layer insertSublayer:self.sqccmLayer atIndex:0];
        [preview dismissViewControllerAnimated:NO completion:^{self.sqccmPreviewController=nil;[self.view setNeedsLayout];[self sqccmUpdatePlayback];if(completion)((void (^)(void))completion)();}];
    }else if(self.presentedViewController)[self dismissViewControllerAnimated:animated completion:completion];
    else if(completion)((void (^)(void))completion)();
}
- (void)sqccmClear {
    [self.sqccmWatchdog invalidate];self.sqccmWatchdog=nil;
    if(self.sqccmObservedItem){[self.sqccmObservedItem removeObserver:self forKeyPath:@"status" context:&SQCCMItemContext];self.sqccmObservedItem=nil;}
    if(self.sqccmObservingPlayer){[self.sqccmPlayer removeObserver:self forKeyPath:@"status" context:&SQCCMPlayerContext];[self.sqccmPlayer removeObserver:self forKeyPath:@"currentItem" context:&SQCCMPlayerContext];self.sqccmObservingPlayer=NO;}
    if(self.sqccmObservingLooper){[self.sqccmLooper removeObserver:self forKeyPath:@"status" context:&SQCCMLooperContext];self.sqccmObservingLooper=NO;}
    [self.sqccmPlayer pause];[self.sqccmLooper disableLooping];self.sqccmLooper=nil;
    [self.sqccmPlayer removeAllItems];self.sqccmPlayer=nil;
    [self.sqccmVideoSource.asset cancelLoading];self.sqccmVideoSource=nil;
    [self.sqccmLayer removeFromSuperlayer];self.sqccmLayer=nil;self.sqccmImage.image=nil;
    self.sqccmButton.hidden=YES;self.sqccmPlaybackFailed=NO;
}
- (void)sqccmShowPlaybackError:(NSError *)error {
    if(self.sqccmPlaybackFailed)return;self.sqccmPlaybackFailed=YES;
    [self.sqccmPlayer pause];self.sqccmButton.hidden=YES;self.sqccmLabel.hidden=NO;
    self.sqccmLabel.text=[NSString stringWithFormat:@"视频播放失败\n%@\n%@ %ld",error.localizedDescription?:@"解码器未就绪",error.domain?:@"AVFoundation",(long)error.code];
    self.sqccmLoadedPath=nil;
}
- (void)sqccmCheckPlayer {
    if(self.sqccmObservedItem!=self.sqccmPlayer.currentItem){
        if(self.sqccmObservedItem)[self.sqccmObservedItem removeObserver:self forKeyPath:@"status" context:&SQCCMItemContext];
        self.sqccmObservedItem=self.sqccmPlayer.currentItem;
        [self.sqccmObservedItem addObserver:self forKeyPath:@"status" options:0 context:&SQCCMItemContext];
    }
    if(self.sqccmPlayer.status==AVPlayerStatusFailed){[self sqccmShowPlaybackError:self.sqccmPlayer.error];return;}
    if(self.sqccmLooper.status==AVPlayerLooperStatusFailed){[self sqccmShowPlaybackError:self.sqccmLooper.error];return;}
    if(self.sqccmObservedItem.status==AVPlayerItemStatusFailed){[self sqccmShowPlaybackError:self.sqccmObservedItem.error];return;}
    if(self.sqccmObservedItem.status==AVPlayerItemStatusReadyToPlay){self.sqccmLabel.hidden=YES;[self sqccmUpdatePlayback];}
}
- (void)observeValueForKeyPath:(NSString *)keyPath ofObject:(id)object change:(NSDictionary *)change context:(void *)context {
    if(context==&SQCCMPlayerContext||context==&SQCCMItemContext||context==&SQCCMLooperContext){
        __weak typeof(self) weakSelf=self;dispatch_async(dispatch_get_main_queue(),^{typeof(self) owner=weakSelf;if(!owner)return;if(object==owner.sqccmPlayer||object==owner.sqccmLooper||object==owner.sqccmObservedItem)[owner sqccmCheckPlayer];});return;
    }
    [super observeValueForKeyPath:keyPath ofObject:object change:change context:context];
}
- (void)sqccmFailedToEnd:(NSNotification *)notification {
    if(notification.object!=self.sqccmPlayer.currentItem&&notification.object!=self.sqccmObservedItem)return;
    NSError *error=notification.userInfo[AVPlayerItemFailedToPlayToEndTimeErrorKey];
    dispatch_async(dispatch_get_main_queue(),^{[self sqccmShowPlaybackError:error];});
}
- (void)sqccmReload {
    if (!self.isViewLoaded) return;
    NSError *error = nil; NSDictionary *root = SQCCMRead(&error);
    NSDictionary *config=SQCCMProfile(root,SQCCM_MODULE_INDEX);
    self.sqccmConfig = config ?: @{};self.view.accessibilityLabel=SQCCMDisplayName(SQCCM_MODULE_INDEX);
    self.view.alpha=SQCCMOpacity(config);
    self.sqccmCaption.text=nil;self.sqccmCaption.hidden=YES;
    self.view.layer.cornerRadius=SQCCMCornerRadius(config);
    self.view.layer.borderWidth=SQCCMBool(config,@"deviceStyle",NO)?3:0;self.view.layer.borderColor=UIColor.blackColor.CGColor;
    NSInteger mode=config[@"contentMode"]?[config[@"contentMode"] integerValue]:1;
    self.sqccmImage.contentMode=mode==1?UIViewContentModeScaleAspectFill:mode==3?UIViewContentModeScaleToFill:UIViewContentModeScaleAspectFit;
    self.sqccmImage.layer.magnificationFilter=SQCCMBool(config,@"pixelArt",NO)?kCAFilterNearest:kCAFilterLinear;
    self.sqccmLayer.videoGravity=mode==1?AVLayerVideoGravityResizeAspectFill:mode==3?AVLayerVideoGravityResize:AVLayerVideoGravityResizeAspect;
    [self.view setNeedsLayout];
    [self.sqccmClock invalidate];self.sqccmClock=nil;
    if(config[@"widget"] && [config[@"widget"] integerValue]<2 && SQCCMBool(config,@"enabled",NO)){
        [self sqccmClear];self.sqccmLoadedPath=nil;[self sqccmTick];__weak typeof(self) weakSelf=self;
        self.sqccmClock=[NSTimer scheduledTimerWithTimeInterval:1 repeats:YES block:^(NSTimer *timer){[weakSelf sqccmTick];}];return;
    }
    NSString *path = SQCCMMediaPath(config);
    BOOL enabled = SQCCMBool(config, @"enabled", NO);
    NSString *identity = enabled ? path : nil;
    if ([identity isEqualToString:self.sqccmLoadedPath]) {
        self.sqccmPlayer.muted = (config[@"sound"]?![config[@"sound"] boolValue]:SQCCMBool(config, @"muted", YES)); [self sqccmUpdatePlayback]; return;
    }
    self.sqccmGeneration++; NSUInteger generation = self.sqccmGeneration;
    self.sqccmLoadedPath = identity; [self sqccmClear]; self.sqccmLabel.hidden = NO;
    if (error) { self.sqccmLabel.text = @"配置无法读取\n请检查设置面板"; return; }
    if (!enabled) { self.sqccmLabel.text = @"骚强媒体\n请在设置中启用并导入"; return; }
    if (!path || ![NSFileManager.defaultManager isReadableFileAtPath:path]) { self.sqccmLabel.text = @"请在设置中导入图片或视频"; self.sqccmLoadedPath = nil; return; }
    NSString *kind = config[@"mediaKind"];
    if ([kind isEqualToString:@"video"]) {
        self.sqccmLabel.text=@"正在载入视频…";
        SQCCM_VIDEO_SOURCE_CLASS *reader=[[SQCCM_VIDEO_SOURCE_CLASS alloc]initWithPath:path error:&error];
        if(!reader){[self sqccmShowPlaybackError:error];return;}
        self.sqccmVideoSource=reader;AVURLAsset *asset=reader.asset;
        __weak typeof(self) weakSelf=self;
        [asset loadValuesAsynchronouslyForKeys:@[@"duration",@"tracks",@"playable"] completionHandler:^{
            (void)reader.asset;NSError *failure=nil;
            for(NSString *key in @[@"duration",@"tracks",@"playable"]){NSError *underlying=nil;if([asset statusOfValueForKey:key error:&underlying]!=AVKeyValueStatusLoaded){failure=underlying?:SQCCMError(40,@"视频属性加载失败");break;}}
            double duration=failure?0:CMTimeGetSeconds(asset.duration);
            if(!failure&&(!asset.playable||![asset tracksWithMediaType:AVMediaTypeVideo].count||!isfinite(duration)||duration<=0))failure=SQCCMError(41,@"视频轨道或时长无效");
            dispatch_async(dispatch_get_main_queue(),^{
                typeof(self) owner=weakSelf;if(!owner||generation!=owner.sqccmGeneration||owner.sqccmVideoSource!=reader)return;
                if(failure){[owner sqccmShowPlaybackError:failure];return;}
                AVPlayerItem *item=[AVPlayerItem playerItemWithAsset:asset];
                owner.sqccmPlayer=[AVQueuePlayer queuePlayerWithItems:@[]];owner.sqccmPlayer.automaticallyWaitsToMinimizeStalling=NO;owner.sqccmLastProgress=CACurrentMediaTime();owner.sqccmLastTime=-1;owner.sqccmPlayer.muted=owner.sqccmConfig[@"sound"]?![owner.sqccmConfig[@"sound"] boolValue]:SQCCMBool(owner.sqccmConfig,@"muted",YES);
                owner.sqccmLooper=[AVPlayerLooper playerLooperWithPlayer:owner.sqccmPlayer templateItem:item];
                [owner.sqccmPlayer addObserver:owner forKeyPath:@"status" options:0 context:&SQCCMPlayerContext];
                [owner.sqccmPlayer addObserver:owner forKeyPath:@"currentItem" options:0 context:&SQCCMPlayerContext];owner.sqccmObservingPlayer=YES;
                [owner.sqccmLooper addObserver:owner forKeyPath:@"status" options:0 context:&SQCCMLooperContext];owner.sqccmObservingLooper=YES;
                owner.sqccmLayer=[AVPlayerLayer playerLayerWithPlayer:owner.sqccmPlayer];NSInteger mode=owner.sqccmConfig[@"contentMode"]?[owner.sqccmConfig[@"contentMode"] integerValue]:1;owner.sqccmLayer.videoGravity=mode==1?AVLayerVideoGravityResizeAspectFill:mode==3?AVLayerVideoGravityResize:AVLayerVideoGravityResizeAspect;
                [owner.view.layer insertSublayer:owner.sqccmLayer atIndex:0];[owner.view setNeedsLayout];[owner sqccmCheckPlayer];[owner sqccmUpdatePlayback];
            });
        }];
    } else {
        self.sqccmLabel.text = @"正在载入图片…";
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
            CGImageSourceRef source = CGImageSourceCreateWithURL((__bridge CFURLRef)[NSURL fileURLWithPath:path], NULL);
            CGImageRef image = source ? CGImageSourceCreateThumbnailAtIndex(source, 0, (__bridge CFDictionaryRef)@{(id)kCGImageSourceCreateThumbnailFromImageAlways:@YES, (id)kCGImageSourceCreateThumbnailWithTransform:@YES, (id)kCGImageSourceThumbnailMaxPixelSize:@1600, (id)kCGImageSourceShouldCacheImmediately:@YES}) : NULL;
            UIImage *decoded = image ? [UIImage imageWithCGImage:image] : nil;
            if (image) CGImageRelease(image); if (source) CFRelease(source);
            dispatch_async(dispatch_get_main_queue(), ^{
                if (generation != self.sqccmGeneration) return;
                self.sqccmImage.image = decoded; self.sqccmLabel.hidden = decoded != nil;
                if (!decoded) { self.sqccmLabel.text = @"图片解码失败，请重新导入"; self.sqccmLoadedPath = nil; }
            });
        });
    }
}
- (void)sqccmTick {
    NSDateFormatter *formatter=[NSDateFormatter new];formatter.dateFormat=[self.sqccmConfig[@"widget"] integerValue]==0?@"HH:mm:ss":@"yyyy年M月d日\nEEEE";
    self.sqccmLabel.text=[formatter stringFromDate:NSDate.date];self.sqccmLabel.hidden=NO;
}
- (void)sqccmToggle {
    BOOL currentlyPlaying = self.sqccmPlayer.rate > 0;
    self.sqccmUserPaused = currentlyPlaying;
    self.sqccmUserRequestedPlay = !currentlyPlaying;
    [self sqccmUpdatePlayback];
}
- (void)sqccmWatchPlayback {
    if(self.sqccmSuspended||!(self.sqccmVisible||self.sqccmPreviewController)||!self.sqccmPlayer)return;
    double position=CMTimeGetSeconds(self.sqccmPlayer.currentTime);CFTimeInterval now=CACurrentMediaTime();
    if(isfinite(position)&&fabs(position-self.sqccmLastTime)>0.02){
        self.sqccmLastTime=position;self.sqccmLastProgress=now;self.sqccmRecoveryStep=0;return;
    }
    if(now-self.sqccmLastProgress<4)return;
    if(self.sqccmNeedsRestart&&!self.sqccmSeekingStart){[self sqccmRestartIfNeeded];return;}
    self.sqccmLastProgress=now;
    if(self.sqccmRecoveryStep++==0){
        AVQueuePlayer *player=self.sqccmPlayer;
        if(player.currentItem.status==AVPlayerItemStatusReadyToPlay){
            CMTime target=isfinite(position)?player.currentTime:kCMTimeZero;
            __weak typeof(self) weakSelf=self;
            [player seekToTime:target toleranceBefore:kCMTimeZero toleranceAfter:kCMTimeZero completionHandler:^(BOOL finished){dispatch_async(dispatch_get_main_queue(),^{typeof(self) owner=weakSelf;if(owner&&owner.sqccmPlayer==player)[owner sqccmUpdatePlayback];});}];
        }else [self sqccmUpdatePlayback];
    }else if(self.sqccmRebuildCount<2&&!self.sqccmPreviewController){
        self.sqccmRebuildCount++;self.sqccmRecoveryStep=0;self.sqccmLoadedPath=nil;[self sqccmReload];
    }else if(self.sqccmPreviewController){[self sqccmUpdatePlayback];}
}
- (void)sqccmRestartIfNeeded {
    if(!self.sqccmNeedsRestart||self.sqccmSeekingStart||!self.sqccmPlayer||self.sqccmPlayer.currentItem.status!=AVPlayerItemStatusReadyToPlay)return;
    self.sqccmSeekingStart=YES;NSUInteger token=self.sqccmPresentationToken;AVQueuePlayer *player=self.sqccmPlayer;
    [player pause];__weak typeof(self) weakSelf=self;
    [player seekToTime:kCMTimeZero toleranceBefore:kCMTimeZero toleranceAfter:kCMTimeZero completionHandler:^(BOOL finished){
        dispatch_async(dispatch_get_main_queue(),^{typeof(self) owner=weakSelf;if(!owner||owner.sqccmPlayer!=player||token!=owner.sqccmPresentationToken)return;
            owner.sqccmSeekingStart=NO;owner.sqccmNeedsRestart=!finished;owner.sqccmLastProgress=CACurrentMediaTime();
            if(finished)[owner sqccmUpdatePlayback];
        });
    }];
}
- (void)sqccmUpdatePlayback {
    BOOL play = !self.sqccmPlaybackFailed && (self.sqccmVisible||self.sqccmPreviewController) && !self.sqccmSuspended;
    BOOL sound=SQCCMBool(self.sqccmConfig,@"sound",!SQCCMBool(self.sqccmConfig,@"muted",YES));self.sqccmPlayer.muted=!play||!sound;self.sqccmPlayer.volume=play&&sound?1:0;
    if (play) {
        [self sqccmRestartIfNeeded];
        if(!self.sqccmNeedsRestart&&!self.sqccmSeekingStart)[self.sqccmPlayer play];
        if(self.sqccmPlayer&&!self.sqccmWatchdog){
            self.sqccmLastTime=-1;self.sqccmLastProgress=CACurrentMediaTime();
            __weak typeof(self) weakSelf=self;
            self.sqccmWatchdog=[NSTimer timerWithTimeInterval:1 repeats:YES block:^(NSTimer *timer){[weakSelf sqccmWatchPlayback];}];
            [[NSRunLoop mainRunLoop] addTimer:self.sqccmWatchdog forMode:NSRunLoopCommonModes];
        }
    } else { [self.sqccmPlayer pause];[self.sqccmWatchdog invalidate];self.sqccmWatchdog=nil; }
    [self.sqccmButton setTitle:play ? @"Ⅱ" : @"▶" forState:UIControlStateNormal];
}
@end

@interface SQCCMModule : NSObject <CCUIContentModule>
@property(nonatomic,strong) SQCCMContentViewController *sqccmController;
@end
@implementation SQCCMModule
- (SQCCMLayoutSize)moduleSizeForOrientation:(int)orientation {
    (void)orientation;NSDictionary *profile=SQCCMProfile(SQCCMRead(NULL),SQCCM_MODULE_INDEX);
    id key=profile[@"moduleSize"];SQCCMGridSize size=SQCCMGridForKey([key isKindOfClass:NSString.class]?[key UTF8String]:NULL);
    return (SQCCMLayoutSize){profile[@"width"]?MAX(1,MIN(4,[profile[@"width"] integerValue])):size.width,profile[@"height"]?MAX(1,MIN(4,[profile[@"height"] integerValue])):size.height};
}
- (UIViewController<CCUIContentModuleContentViewController> *)contentViewController {
    if (!self.sqccmController) self.sqccmController = [SQCCMContentViewController new]; return self.sqccmController;
}
- (UIViewController *)backgroundViewController { return nil; }
@end
