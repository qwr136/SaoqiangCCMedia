from pathlib import Path
p=Path(__file__).resolve().parents[1]/'Module/SQCCMModule.m'
s=p.read_text()
s=s.replace('#import "../Shared/SQCCMStorage.h"', '''#import "../Shared/SQCCMStorage.h"
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
''')
s=s.replace('@property(nonatomic,strong) AVPlayerLayer *sqccmLayer;', '''@property(nonatomic,strong) AVPlayerLayer *sqccmLayer;
@property(nonatomic,strong) SQCCM_VIDEO_SOURCE_CLASS *sqccmVideoSource;
@property(nonatomic,strong) AVPlayerItem *sqccmObservedItem;
@property(nonatomic) BOOL sqccmObservingPlayer;
@property(nonatomic) BOOL sqccmObservingLooper;
@property(nonatomic) BOOL sqccmPlaybackFailed;''')
s=s.replace('    [_sqccmPlayer pause];','    [self sqccmClear];')
s=s.replace('- (BOOL)providesOwnPlatter { return NO; }','- (BOOL)providesOwnPlatter { return YES; }')
a=s.index('- (void)sqccmClear {');b=s.index('- (void)sqccmReload {',a)
s=s[:a]+'''- (void)sqccmClear {
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
    self.sqccmLabel.text=[NSString stringWithFormat:@"视频播放失败\\n%@\\n%@ %ld",error.localizedDescription?:@"解码器未就绪",error.domain?:@"AVFoundation",(long)error.code];
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
    if(self.sqccmObservedItem.status==AVPlayerItemStatusReadyToPlay){self.sqccmLabel.hidden=YES;self.sqccmButton.hidden=NO;}
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
''' +s[b:]
s=s.replace('NSDictionary *config = SQCCMRead(&error);','NSDictionary *root = SQCCMRead(&error);\n    NSDictionary *config=SQCCMProfile(root,SQCCM_MODULE_INDEX);')
s=s.replace('    self.sqccmConfig = config ?: @{};','    self.sqccmConfig = config ?: @{};\n    self.view.alpha=SQCCMOpacity(config);')
a=s.index('        AVPlayerItem *item = [AVPlayerItem playerItemWithURL:');b=s.index('    } else {',a)
s=s[:a]+'''        self.sqccmLabel.text=@"正在载入视频…";
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
                owner.sqccmPlayer=[AVQueuePlayer queuePlayerWithItems:@[]];owner.sqccmPlayer.muted=SQCCMBool(owner.sqccmConfig,@"muted",YES);
                owner.sqccmLooper=[AVPlayerLooper playerLooperWithPlayer:owner.sqccmPlayer templateItem:item];
                [owner.sqccmPlayer addObserver:owner forKeyPath:@"status" options:0 context:&SQCCMPlayerContext];
                [owner.sqccmPlayer addObserver:owner forKeyPath:@"currentItem" options:0 context:&SQCCMPlayerContext];owner.sqccmObservingPlayer=YES;
                [owner.sqccmLooper addObserver:owner forKeyPath:@"status" options:0 context:&SQCCMLooperContext];owner.sqccmObservingLooper=YES;
                owner.sqccmLayer=[AVPlayerLayer playerLayerWithPlayer:owner.sqccmPlayer];owner.sqccmLayer.videoGravity=AVLayerVideoGravityResizeAspect;
                [owner.view.layer insertSublayer:owner.sqccmLayer atIndex:0];[owner.view setNeedsLayout];[owner sqccmCheckPlayer];[owner sqccmUpdatePlayback];
            });
        }];
''' +s[b:]
s=s.replace('    BOOL play = self.sqccmVisible','    BOOL play = !self.sqccmPlaybackFailed && self.sqccmVisible')
s=s.replace('name:UIApplicationWillResignActiveNotification object:nil];','name:UIApplicationWillResignActiveNotification object:nil];\n        [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(sqccmFailedToEnd:) name:AVPlayerItemFailedToPlayToEndTimeNotification object:nil];')
s=s.replace('@implementation SQCCMModule\n','''@implementation SQCCMModule
- (SQCCMLayoutSize)moduleSizeForOrientation:(NSInteger)orientation {
    (void)orientation;NSDictionary *profile=SQCCMProfile(SQCCMRead(NULL),SQCCM_MODULE_INDEX);
    id key=profile[@"moduleSize"];SQCCMGridSize size=SQCCMGridForKey([key isKindOfClass:NSString.class]?[key UTF8String]:NULL);
    return (SQCCMLayoutSize){size.width,size.height};
}
''')
p.write_text(s)
print('Updated',p)
