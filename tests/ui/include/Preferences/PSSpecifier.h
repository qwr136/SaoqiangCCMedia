#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

@class PSSpecifier;

typedef NS_ENUM(NSInteger, PSCellType) {
    PSLinkCell = 1,
};

@interface PSSpecifier : NSObject
@property(nonatomic, weak) id target;
@property(nonatomic, assign) Class detail;
@property(nonatomic, copy, readonly) NSString *name;
+ (instancetype)groupSpecifierWithName:(NSString *)name;
+ (instancetype)preferenceSpecifierNamed:(NSString *)name target:(id)target set:(SEL)set get:(SEL)get detail:(Class)detail cell:(NSInteger)cell edit:(Class)edit;
- (id)initWithPropertyList:(NSDictionary *)properties target:(id)target;
- (id)propertyForKey:(NSString *)key;
- (void)setProperty:(id)value forKey:(NSString *)key;
@end
