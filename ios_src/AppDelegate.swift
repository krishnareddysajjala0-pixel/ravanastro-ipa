import UIKit
import Capacitor
import CoreLocation
import WebKit

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate, CLLocationManagerDelegate, WKUIDelegate, WKScriptMessageHandler {

    var window: UIWindow?
    var locationManager: CLLocationManager?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        print("[RavanAstro] Launching embedded offline Python engine...")
        setupLocationManager()
        startEmbeddedPython()
        waitForServer()
        setupWebViewGeolocation()
        return true
    }

    private func setupLocationManager() {
        DispatchQueue.main.async {
            let manager = CLLocationManager()
            manager.delegate = self
            manager.desiredAccuracy = kCLLocationAccuracyBest
            manager.requestWhenInUseAuthorization()
            manager.startUpdatingLocation()
            self.locationManager = manager
            print("[Location] CLLocationManager initialized and requested authorization")
        }
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard let loc = locations.last else { return }
        let lat = loc.coordinate.latitude
        let lon = loc.coordinate.longitude
        print("[Location] Native iOS GPS coordinate updated: \(lat), \(lon)")

        let pySync = """
import os
os.environ['DEVICE_LAT'] = '\(lat)'
os.environ['DEVICE_LON'] = '\(lon)'
"""
        RunPythonCode(pySync)
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        print("[Location] CLLocationManager error: \(error.localizedDescription)")
    }

    private func setupWebViewGeolocation() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) {
            if let rootVC = self.window?.rootViewController as? CAPBridgeViewController,
               let webView = rootVC.webView {
                webView.uiDelegate = self
                webView.configuration.userContentController.add(self, name: "nativePrint")
                
                let printOverrideScript = WKUserScript(
                    source: """
                    window.print = function() {
                        if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.nativePrint) {
                            window.webkit.messageHandlers.nativePrint.postMessage('print');
                        }
                    };
                    """,
                    injectionTime: .atDocumentStart,
                    forMainFrameOnly: false
                )
                webView.configuration.userContentController.addUserScript(printOverrideScript)
                print("[WebKit] Attached WKUIDelegate and nativePrint message handler")
            }
        }
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        if message.name == "nativePrint" {
            DispatchQueue.main.async {
                guard let rootVC = self.window?.rootViewController as? CAPBridgeViewController,
                      let webView = rootVC.webView else { return }
                let printController = UIPrintInteractionController.shared
                let printInfo = UIPrintInfo(dictionary: nil)
                printInfo.outputType = .general
                printInfo.jobName = "Ravan Astro Horoscope"
                printController.printInfo = printInfo
                printController.printFormatter = webView.viewPrintFormatter()
                printController.present(animated: true, completionHandler: nil)
                print("[Print] Presented UIPrintInteractionController")
            }
        }
    }

    @available(iOS 15.0, *)
    func webView(_ webView: WKWebView, requestGeolocationPermissionFor origin: WKSecurityOrigin, initiatedBy frame: WKFrameInfo, decisionHandler: @escaping (WKPermissionDecision) -> Void) {
        print("[WebKit] Auto-granting geolocation permission for \(origin.host)")
        decisionHandler(.grant)
    }

    private func startEmbeddedPython() {
        guard let resourcePath = Bundle.main.resourcePath else {
            print("[Python] Error: resourcePath is nil")
            return
        }

        let pyHome = "\(resourcePath)/python"
        let pyLib = "\(pyHome)/lib/python3.11"
        let pySite = "\(pyLib)/site-packages"
        let appDir = "\(resourcePath)/python_app"
        let pyPath = "\(appDir):\(pyLib):\(pySite)"

        print("[Python] Calling StartPythonEngine...")
        StartPythonEngine(pyHome, pyPath, resourcePath)
        print("[Python] Python engine initialized!")

        DispatchQueue.global(qos: .userInitiated).async {
            print("[Python] Background runner thread launched")
            let runnerScript = """
import sys, os
app_dir = os.environ.get('RESOURCE_PATH', '') + '/python_app'
if app_dir not in sys.path:
    sys.path.insert(0, app_dir)
try:
    import app
    print('[Python] Starting Flask on 127.0.0.1:5000...', flush=True)
    app.app.run(host='127.0.0.1', port=5000, threaded=True, use_reloader=False)
except Exception as e:
    print(f'[Python Flask Crash] {e}', flush=True)
"""
            RunPythonCode(runnerScript)
        }
    }

    private func waitForServer() {
        var serverReady = false
        let start = Date()
        while !serverReady && Date().timeIntervalSince(start) < 8.0 {
            if let url = URL(string: "http://127.0.0.1:5000/") {
                var request = URLRequest(url: url)
                request.timeoutInterval = 0.4
                let sema = DispatchSemaphore(value: 0)
                let task = URLSession.shared.dataTask(with: request) { (_, response, _) in
                    if let httpResponse = response as? HTTPURLResponse, (200...399).contains(httpResponse.statusCode) {
                        serverReady = true
                    }
                    sema.signal()
                }
                task.resume()
                _ = sema.wait(timeout: .now() + 0.5)
            }
            if !serverReady {
                Thread.sleep(forTimeInterval: 0.15)
            }
        }
        print("[Python] Server ready: \(serverReady)")
    }

    func applicationWillResignActive(_ application: UIApplication) {}
    func applicationDidEnterBackground(_ application: UIApplication) {}
    func applicationWillEnterForeground(_ application: UIApplication) {}
    func applicationDidBecomeActive(_ application: UIApplication) {}
    func applicationWillTerminate(_ application: UIApplication) {}
}
