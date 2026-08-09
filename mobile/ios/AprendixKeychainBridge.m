#import "AprendixKeychainBridge.h"
#import <Security/Security.h>
#import <UIKit/UIKit.h>
#import <UserNotifications/UserNotifications.h>
#import <Vision/Vision.h>

@implementation AprendixKeychainBridge
+ (NSString *)recognizeTextAtPath:(NSString *)path {
    UIImage *image = [UIImage imageWithContentsOfFile:path];
    if (image.CGImage == nil) return @"";
    __block NSArray<VNRecognizedTextObservation *> *observations = @[];
    __block NSError *requestError = nil;
    VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc]
        initWithCompletionHandler:^(VNRequest *finished, NSError *error) {
            requestError = error;
            observations = (NSArray<VNRecognizedTextObservation *> *)finished.results ?: @[];
        }];
    request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
    request.usesLanguageCorrection = NO;
    VNImageRequestHandler *handler = [[VNImageRequestHandler alloc] initWithCGImage:image.CGImage options:@{}];
    if (![handler performRequests:@[request] error:&requestError] || requestError) return @"";
    NSMutableArray<NSString *> *lines = [NSMutableArray array];
    for (VNRecognizedTextObservation *observation in observations) {
        VNRecognizedText *candidate = [[observation topCandidates:1] firstObject];
        if (candidate.string.length) [lines addObject:candidate.string];
    }
    return [lines componentsJoinedByString:@"\n"];
}
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
