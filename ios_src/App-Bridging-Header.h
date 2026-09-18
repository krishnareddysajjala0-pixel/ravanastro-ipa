#ifndef App_Bridging_Header_h
#define App_Bridging_Header_h

#include <Python.h>
#include <stdlib.h>

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
