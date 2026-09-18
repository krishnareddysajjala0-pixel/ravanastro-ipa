#ifndef App_Bridging_Header_h
#define App_Bridging_Header_h

#if __has_include(<Python/Python.h>)
#import <Python/Python.h>
#elif __has_include(<Python.h>)
#import <Python.h>
#endif
#import <stdlib.h>

static inline void StartPythonEngine(const char *pyHome, const char *pyPath, const char *resourcePath) {
    setenv("PYTHONHOME", pyHome, 1);
    setenv("PYTHONPATH", pyPath, 1);
    setenv("PYTHONUNBUFFERED", "1", 1);
    setenv("RESOURCE_PATH", resourcePath, 1);
    Py_Initialize();
}

static inline int RunPythonCode(const char *code) {
    return PyRun_SimpleString(code);
}

#endif /* App_Bridging_Header_h */
