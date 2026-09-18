require 'xcodeproj'

project_path = 'App.xcodeproj'
project = Xcodeproj::Project.open(project_path)
target = project.targets.find { |t| t.name == 'App' } || project.targets.first

target.build_configurations.each do |config|
  config.build_settings['SWIFT_OBJC_BRIDGING_HEADER'] = 'App/App-Bridging-Header.h'
  config.build_settings['HEADER_SEARCH_PATHS'] ||= ['$(inherited)']
  config.build_settings['HEADER_SEARCH_PATHS'] << '$(PROJECT_DIR)/Frameworks/Python.xcframework/ios-arm64/Python.framework/Headers'
  config.build_settings['HEADER_SEARCH_PATHS'] << '$(PROJECT_DIR)/Frameworks/Python.xcframework/ios-arm64/include/python3.11'
  
  config.build_settings['FRAMEWORK_SEARCH_PATHS'] ||= ['$(inherited)']
  config.build_settings['FRAMEWORK_SEARCH_PATHS'] << '$(PROJECT_DIR)/Frameworks/Python.xcframework/ios-arm64'
  config.build_settings['FRAMEWORK_SEARCH_PATHS'] << '$(PROJECT_DIR)/Frameworks'
  
  config.build_settings['OTHER_LDFLAGS'] ||= ['$(inherited)']
  config.build_settings['OTHER_LDFLAGS'] << '-F$(PROJECT_DIR)/Frameworks/Python.xcframework/ios-arm64 -framework Python'
  config.build_settings['ENABLE_BITCODE'] = 'NO'
end

project.save
puts 'Successfully configured App target build settings in App.xcodeproj!'
