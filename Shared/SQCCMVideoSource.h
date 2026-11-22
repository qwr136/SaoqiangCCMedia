#pragma once
#import <AVFoundation/AVFoundation.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#include <fcntl.h>
#include <unistd.h>
#include <sys/stat.h>
#include <errno.h>
#include <limits.h>
#ifndef SQCCM_VIDEO_SOURCE_CLASS
#define SQCCM_VIDEO_SOURCE_CLASS SQCCMVideoSource
#endif
// Only this in-process object opens the jbroot file. AVFoundation receives byte
// ranges through a custom asset URL rather than opening a randomized path itself.
@interface SQCCM_VIDEO_SOURCE_CLASS : NSObject <AVAssetResourceLoaderDelegate>
@property(nonatomic,strong,readonly) AVURLAsset *asset;
- (instancetype)initWithPath:(NSString *)path error:(NSError **)error;
@end
@implementation SQCCM_VIDEO_SOURCE_CLASS {
    int _sqccmFD;
    long long _sqccmLength;
    NSString *_sqccmType;
    dispatch_queue_t _sqccmQueue;
}
- (instancetype)initWithPath:(NSString *)path error:(NSError **)error {
    if((self=[super init])){
        _sqccmFD=-1;
        int fd=open(path.fileSystemRepresentation,O_RDONLY|O_NOFOLLOW|O_NONBLOCK|O_CLOEXEC);
        struct stat st;
        if(fd<0||fstat(fd,&st)||!S_ISREG(st.st_mode)||st.st_size<=0){if(fd>=0)close(fd);if(error)*error=[NSError errorWithDomain:NSPOSIXErrorDomain code:errno?:EINVAL userInfo:@{NSLocalizedDescriptionKey:@"视频文件无法读取或不是普通文件"}];return nil;}
        _sqccmFD=fd;_sqccmLength=st.st_size;
        _sqccmType=[path.pathExtension.lowercaseString isEqual:@"mov"]?@"com.apple.quicktime-movie":@"public.mpeg-4";
        NSURL *url=[NSURL URLWithString:[NSString stringWithFormat:@"sqccmedia://local/%@.%@",NSUUID.UUID.UUIDString,path.pathExtension.lowercaseString]];
        _asset=[AVURLAsset URLAssetWithURL:url options:nil];
        _sqccmQueue=dispatch_queue_create("com.saoqiang.ccmedia.video-ranges",DISPATCH_QUEUE_SERIAL);
        [_asset.resourceLoader setDelegate:self queue:_sqccmQueue];
    }return self;
}
- (void)dealloc { if(_sqccmFD>=0)close(_sqccmFD); }
- (BOOL)resourceLoader:(AVAssetResourceLoader *)loader shouldWaitForLoadingOfRequestedResource:(AVAssetResourceLoadingRequest *)request {
    (void)loader;
    AVAssetResourceLoadingContentInformationRequest *info=request.contentInformationRequest;
    if(info){info.contentType=_sqccmType;info.contentLength=_sqccmLength;info.byteRangeAccessSupported=YES;}
    AVAssetResourceLoadingDataRequest *data=request.dataRequest;
    if(!data){[request finishLoading];return YES;}
    long long offset=MAX(data.currentOffset,data.requestedOffset);
    long long end=_sqccmLength;
    if(!data.requestsAllDataToEndOfResource){
        if(data.requestedOffset<0||data.requestedLength<0||data.requestedOffset>LLONG_MAX-(long long)data.requestedLength){[request finishLoadingWithError:[NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorBadURL userInfo:nil]];return YES;}
        end=MIN(end,data.requestedOffset+(long long)data.requestedLength);
    }
    if(offset<0||offset>_sqccmLength){[request finishLoadingWithError:[NSError errorWithDomain:NSURLErrorDomain code:NSURLErrorCannotDecodeContentData userInfo:nil]];return YES;}
    unsigned char buffer[65536];
    while(offset<end&&!request.cancelled){
        size_t count=(size_t)MIN((long long)sizeof(buffer),end-offset);
        ssize_t n=pread(_sqccmFD,buffer,count,(off_t)offset);
        if(n<0&&errno==EINTR)continue;
        if(n<=0){[request finishLoadingWithError:[NSError errorWithDomain:NSPOSIXErrorDomain code:n<0?errno:EIO userInfo:nil]];return YES;}
        @autoreleasepool { [data respondWithData:[NSData dataWithBytes:buffer length:(NSUInteger)n]]; }
        offset+=n;
    }
    if(!request.cancelled)[request finishLoading];return YES;
}
- (void)resourceLoader:(AVAssetResourceLoader *)loader didCancelLoadingRequest:(AVAssetResourceLoadingRequest *)request { (void)loader;(void)request; }
@end
