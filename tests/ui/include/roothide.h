#import <Foundation/Foundation.h>

// Simulator-only replacement. Every logical root path stays inside this app's container.
static inline NSString *jbroot(NSString *logicalPath) {
    NSString *relative = [logicalPath hasPrefix:@"/"] ? [logicalPath substringFromIndex:1] : logicalPath;
    return [[NSHomeDirectory() stringByAppendingPathComponent:@"SQCCMTestRoot"] stringByAppendingPathComponent:relative];
}
