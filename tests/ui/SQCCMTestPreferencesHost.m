#import <Preferences/PSListController.h>
#import <Preferences/PSSpecifier.h>
#import <Preferences/PSTableCell.h>
#import <objc/runtime.h>

@implementation PSSpecifier {
    NSMutableDictionary *_properties;
    NSString *_name;
}
+ (instancetype)groupSpecifierWithName:(NSString *)name {
    PSSpecifier *specifier = [[self alloc] initWithPropertyList:@{@"label": [name copy] ?: @"", @"cell": @"PSGroupCell"} target:nil];
    return specifier;
}
+ (instancetype)preferenceSpecifierNamed:(NSString *)name target:(id)target set:(SEL)set get:(SEL)get detail:(Class)detail cell:(NSInteger)cell edit:(Class)edit {
    PSSpecifier *specifier = [[self alloc] initWithPropertyList:@{@"label": [name copy] ?: @"", @"cell": @(cell)} target:target];
    specifier.detail = detail;
    if (set) [specifier setProperty:NSStringFromSelector(set) forKey:@"set"];
    if (get) [specifier setProperty:NSStringFromSelector(get) forKey:@"get"];
    if (edit) [specifier setProperty:edit forKey:@"edit"];
    return specifier;
}
- (instancetype)initWithPropertyList:(NSDictionary *)properties target:(id)target {
    NSParameterAssert([properties isKindOfClass:NSDictionary.class]);
    if ((self = [super init])) {
        _properties = [properties mutableCopy];
        id label = _properties[@"label"];
        _name = [label isKindOfClass:NSString.class] ? [label copy] : @"";
        _target = target;
    }
    return self;
}
- (NSString *)name { return _name; }
- (id)propertyForKey:(NSString *)key { return _properties[key]; }
- (void)setProperty:(id)value forKey:(NSString *)key {
    if (!key) return;
    if (value) _properties[key] = value;
    else [_properties removeObjectForKey:key];
}
@end

@implementation PSTableCell
- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString *)reuseIdentifier specifier:(PSSpecifier *)specifier {
    (void)specifier;
    return [super initWithStyle:style reuseIdentifier:reuseIdentifier];
}
- (void)refreshCellContentsWithSpecifier:(PSSpecifier *)specifier { (void)specifier; }
@end

@implementation PSListController
- (void)viewDidLoad {
    [super viewDidLoad];
    self.tableView.dataSource = (id<UITableViewDataSource>)self;
    self.tableView.delegate = (id<UITableViewDelegate>)self;
    self.tableView.rowHeight = UITableViewAutomaticDimension;
    self.tableView.estimatedRowHeight = 52;
    [self.tableView reloadData];
}
- (NSArray *)specifiers { return _specifiers ?: @[]; }
- (NSArray<PSSpecifier *> *)loadSpecifiersFromPlistName:(NSString *)name target:(id)target {
    NSString *root = NSBundle.mainBundle.resourcePath;
    NSString *path = [root stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"plist"]];
    if (![[NSFileManager defaultManager] fileExistsAtPath:path]) [NSException raise:NSInternalInconsistencyException format:@"Missing bundled specifier resource %@.plist", name];
    NSDictionary *rootPlist = [NSDictionary dictionaryWithContentsOfFile:path];
    NSArray *items = rootPlist[@"items"];
    if (![items isKindOfClass:NSArray.class]) [NSException raise:NSInvalidArgumentException format:@"Invalid specifier root %@", path];
    NSMutableArray *specifiers = [NSMutableArray arrayWithCapacity:items.count];
    for (id item in items) {
        if (![item isKindOfClass:NSDictionary.class]) [NSException raise:NSInvalidArgumentException format:@"Invalid specifier item"];
        [specifiers addObject:[[PSSpecifier alloc] initWithPropertyList:item target:target]];
    }
    return specifiers;
}
- (void)reloadSpecifiers {
    if (self.isViewLoaded) [self.tableView reloadData];
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:NO];
    if ((NSUInteger)indexPath.row >= self.specifiers.count) return;
    PSSpecifier *specifier = self.specifiers[(NSUInteger)indexPath.row];
    Class detail = specifier.detail;
    if (!detail || ![detail isSubclassOfClass:PSListController.class]) return;
    PSListController *controller = [[detail alloc] initWithStyle:UITableViewStyleInsetGrouped];
    [((UIViewController *)specifier.target).navigationController pushViewController:controller animated:NO];
}
- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { (void)tableView; return 1; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    (void)tableView; (void)section; return (NSInteger)self.specifiers.count;
}
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    PSSpecifier *specifier = self.specifiers[(NSUInteger)indexPath.row];
            id candidate = [specifier propertyForKey:@"cellClass"];
    Class cellClass = Nil;
    if (object_isClass(candidate)) cellClass = candidate;
    else if ([candidate isKindOfClass:NSString.class]) cellClass = NSClassFromString(candidate);
    UITableViewCell *cell = nil;
    if (cellClass && [cellClass isSubclassOfClass:PSTableCell.class]) {
        cell = [[cellClass alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:nil specifier:specifier];
    } else {
        cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
    }
    if ([cell isKindOfClass:PSTableCell.class]) [(PSTableCell *)cell refreshCellContentsWithSpecifier:specifier];
    id label = [specifier propertyForKey:@"label"];
    if (label && cell.textLabel.text.length == 0) cell.textLabel.text = [label description];
    id footer = [specifier propertyForKey:@"footerText"];
    if ([footer isKindOfClass:NSString.class] && [footer length]) cell.detailTextLabel.text = footer;
    return cell;
}
@end
