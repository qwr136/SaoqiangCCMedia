#import <UIKit/UIKit.h>

@class PSSpecifier;

// Test-only stand-in; this is not Apple's private iOS Preferences framework.
@interface PSListController : UITableViewController {
@protected
    NSArray *_specifiers;
}
- (NSArray *)specifiers;
- (NSArray<PSSpecifier *> *)loadSpecifiersFromPlistName:(NSString *)name target:(id)target;
- (void)reloadSpecifiers;
@end
