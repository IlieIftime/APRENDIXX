#import <Foundation/Foundation.h>

@interface AprendixKeychainBridge : NSObject
// Local Vision OCR. The caller must run this outside the UI thread.
+ (NSString *)recognizeTextAtPath:(NSString *)path;
+ (NSData *)keyForService:(NSString *)service account:(NSString *)account;
+ (BOOL)storeKey:(NSData *)key service:(NSString *)service account:(NSString *)account;
+ (void)haptic:(NSString *)pattern;
+ (BOOL)scheduleAt:(double)epoch identifier:(NSString *)identifier title:(NSString *)title body:(NSString *)body;
@end
