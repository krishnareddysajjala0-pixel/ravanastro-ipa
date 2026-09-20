import UIKit
import Capacitor
import WebKit

@UIApplicationMain
class AppDelegate: UIResponder, UIApplicationDelegate, WKScriptMessageHandler {

    var window: UIWindow?
    private var webView: WKWebView?

    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        print("[RavanAstro] Launching embedded offline Python engine...")
        startEmbeddedPython()
        waitForServer()
        setupNativePrintBridge()
        return true
    }

    private func setupNativePrintBridge() {
        var attempts = 0
        func tryAttach() {
            attempts += 1
            if let rootVC = self.window?.rootViewController {
                if let wv = self.findWebView(in: rootVC.view) {
                    self.webView = wv
                    let ucc = wv.configuration.userContentController
                    ucc.removeScriptMessageHandler(forName: "nativePrint")
                    ucc.add(self, name: "nativePrint")
                    ucc.removeScriptMessageHandler(forName: "nativeSavePDF")
                    ucc.add(self, name: "nativeSavePDF")

                    print("[RavanAstro] Successfully registered nativePrint & nativeSavePDF on WKWebView!")
                    return
                }
            }
            if attempts < 25 {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
                    tryAttach()
                }
            }
        }
        DispatchQueue.main.async {
            tryAttach()
        }
    }

    private func findWebView(in view: UIView) -> WKWebView? {
        if let wv = view as? WKWebView {
            return wv
        }
        for subview in view.subviews {
            if let found = findWebView(in: subview) {
                return found
            }
        }
        return nil
    }

    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        guard let wv = self.webView ?? message.webView ?? self.findWebView(in: self.window?.rootViewController?.view ?? UIView()) else {
            print("[RavanAstro] Error: WKWebView not found for message \(message.name)")
            return
        }

        var title = "RavanAstro_Kundali"
        if let dict = message.body as? [String: Any], let t = dict["title"] as? String, !t.isEmpty {
            title = t
        } else if let s = message.body as? String, !s.isEmpty {
            title = s
        }

        if message.name == "nativePrint" {
            DispatchQueue.main.async {
                let printController = UIPrintInteractionController.shared
                let printInfo = UIPrintInfo(dictionary: nil)
                printInfo.outputType = .general
                printInfo.jobName = title
                printController.printInfo = printInfo
                printController.printFormatter = wv.viewPrintFormatter()
                printController.showsNumberOfCopies = true
                printController.showsPageRange = true

                if let rootVC = self.window?.rootViewController {
                    if let popover = printController.popoverPresentationController {
                        popover.sourceView = rootVC.view
                        popover.sourceRect = CGRect(x: rootVC.view.bounds.midX, y: rootVC.view.bounds.midY, width: 0, height: 0)
                        popover.permittedArrowDirections = []
                    }
                    printController.present(animated: true) { (controller, completed, error) in
                        if let error = error {
                            print("[RavanAstro] Print error: \(error)")
                        } else {
                            print("[RavanAstro] Print completed: \(completed)")
                        }
                    }
                }
            }
        } else if message.name == "nativeSavePDF" {
            DispatchQueue.main.async {
                self.exportNativePDF(from: wv, title: title)
            }
        }
    }

    private func exportNativePDF(from wv: WKWebView, title: String) {
        let printPageRenderer = UIPrintPageRenderer()
        printPageRenderer.addPrintFormatter(wv.viewPrintFormatter(), startingAtPageAt: 0)

        // Standard A4 Paper: 595.2 x 841.8 points (210mm x 297mm)
        let paperRect = CGRect(x: 0, y: 0, width: 595.2, height: 841.8)
        let printableRect = CGRect(x: 12.0, y: 12.0, width: 571.2, height: 817.8)
        printPageRenderer.setValue(NSValue(cgRect: paperRect), forKey: "paperRect")
        printPageRenderer.setValue(NSValue(cgRect: printableRect), forKey: "printableRect")

        let pdfData = NSMutableData()
        UIGraphicsBeginPDFContextToData(pdfData, paperRect, nil)
        for i in 0..<printPageRenderer.numberOfPages {
            UIGraphicsBeginPDFPage()
            printPageRenderer.drawPage(at: i, in: UIGraphicsGetPDFContextBounds())
        }
        UIGraphicsEndPDFContext()

        let safeTitle = title.replacingOccurrences(of: "/", with: "_")
                             .replacingOccurrences(of: ":", with: "_")
                             .replacingOccurrences(of: " ", with: "_")
                             .trimmingCharacters(in: .whitespacesAndNewlines)
        let filename = (safeTitle.isEmpty ? "RavanAstro_Kundali" : safeTitle) + ".pdf"
        let tempURL = FileManager.default.temporaryDirectory.appendingPathComponent(filename)

        do {
            try pdfData.write(to: tempURL)
            let activityVC = UIActivityViewController(activityItems: [tempURL], applicationActivities: nil)
            if let rootVC = self.window?.rootViewController {
                if let popover = activityVC.popoverPresentationController {
                    popover.sourceView = rootVC.view
                    popover.sourceRect = CGRect(x: rootVC.view.bounds.midX, y: rootVC.view.bounds.midY, width: 0, height: 0)
                    popover.permittedArrowDirections = []
                }
                rootVC.present(activityVC, animated: true, completion: nil)
            }
        } catch {
            print("[RavanAstro] Error writing PDF: \(error)")
        }
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
