#pragma once
#include <math.h>
#include <stddef.h>
#include <string.h>
typedef struct { unsigned long width,height; } SQCCMGridSize;
static inline SQCCMGridSize SQCCMGridForKey(const char *key) {
    if(key && strlen(key)==3 && key[1]=='x' && key[0]>='1' && key[0]<='4' && key[2]>='1' && key[2]<='4')return (SQCCMGridSize){key[0]-'0',key[2]-'0'};
    return (SQCCMGridSize){2,2};
}
static inline double SQCCMClampOpacity(double value) {
    return !isfinite(value)?1.0:value<0?0:value>1?1:value;
}
