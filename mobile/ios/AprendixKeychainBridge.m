#import "AprendixKeychainBridge.h"
#import <Security/Security.h>
#import <UIKit/UIKit.h>
#import <UserNotifications/UserNotifications.h>

@implementation AprendixKeychainBridge
+ (NSMutableDictionary *)query:(NSString *)service account:(NSString *)account {
    return [@{(__bridge id)kSecClass: (__bridge id)kSecClassGenericPassword,
              (__bridge id)kSecAttrService: service,
              (__bridge id)kSecAttrAccount: account} mutableCopy];
}
+ (NSData *)keyForService:(NSString *)service account:(NSString *)account {
    NSMutableDictionary *query = [self query:service account:account];
    query[(__bridge id)kSecReturnData] = @YES;
    query[(__bridge id)kSecMatchLimit] = (__bridge id)kSecMatchLimitOne;
    CFTypeRef result = NULL;
    OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)query, &result);
    if (status == errSecItemNotFound) return nil;
    if (status != errSecSuccess) return nil;
    return CFBridgingRelease(result);
}
+ (BOOL)storeKey:(NSData *)key service:(NSString *)service account:(NSString *)account {
    NSMutableDictionary *query = [self query:service account:account];
    SecItemDelete((__bridge CFDictionaryRef)query);
    query[(__bridge id)kSecValueData] = key;
    query[(__bridge id)kSecAttrAccessible] = (__bridge id)kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly;
    return SecItemAdd((__bridge CFDictionaryRef)query, NULL) == errSecSuccess;
}
+ (void)haptic:(NSString *)pattern {
    UIImpactFeedbackStyle style = [pattern isEqualToString:@"error"] ? UIImpactFeedbackStyleHeavy : UIImpactFeedbackStyleLight;
    UIImpactFeedbackGenerator *generator = [[UIImpactFeedbackGenerator alloc] initWithStyle:style];
    [generator prepare]; [generator impactOccurred];
}
+ (BOOL)scheduleAt:(double)epoch identifier:(NSString *)identifier title:(NSString *)title body:(NSString *)body {
    [UNUserNotificationCenter.currentNotificationCenter
        requestAuthorizationWithOptions:(UNAuthorizationOptionAlert | UNAuthorizationOptionSound)
        completionHandler:^(BOOL granted, NSError *error) {}];
    UNMutableNotificationContent *content = [UNMutableNotificationContent new];
    content.title = title; content.body = body; content.sound = UNNotificationSound.defaultSound;
    NSTimeInterval interval = MAX(1.0, epoch - NSDate.date.timeIntervalSince1970);
    UNTimeIntervalNotificationTrigger *trigger = [UNTimeIntervalNotificationTrigger triggerWithTimeInterval:interval repeats:NO];
    UNNotificationRequest *request = [UNNotificationRequest requestWithIdentifier:identifier content:content trigger:trigger];
    [UNUserNotificationCenter.currentNotificationCenter addNotificationRequest:request withCompletionHandler:nil];
    return YES;
}
@end
