require 'xcodeproj'

project_path = 'ios/App/App.xcodeproj'
project = Xcodeproj::Project.open(project_path)
target = project.targets.first

# 1. Update Build Settings
target.build_configurations.each do |config|
  config.build_settings['FRAMEWORK_SEARCH_PATHS'] ||= ['$(inherited)']
  config.build_settings['FRAMEWORK_SEARCH_PATHS'] << '$(PROJECT_DIR)/Frameworks' unless config.build_settings['FRAMEWORK_SEARCH_PATHS'].include?('$(PROJECT_DIR)/Frameworks')
  config.build_settings['FRAMEWORK_SEARCH_PATHS'] << '$(PROJECT_DIR)/Frameworks/**' unless config.build_settings['FRAMEWORK_SEARCH_PATHS'].include?('$(PROJECT_DIR)/Frameworks/**')
  
  config.build_settings['SWIFT_OBJC_BRIDGING_HEADER'] = 'App/App-Bridging-Header.h'
  config.build_settings['ENABLE_BITCODE'] = 'NO'
  config.build_settings['ALWAYS_EMBED_SWIFT_STANDARD_LIBRARIES'] = 'YES'
  config.build_settings['OTHER_LDFLAGS'] ||= ['$(inherited)']
  config.build_settings['OTHER_LDFLAGS'] << '-framework Python' unless config.build_settings['OTHER_LDFLAGS'].include?('-framework Python')
end

# 2. Add Bridging Header
app_group = project.main_group.find_subpath('App', true)
bridging_header_file = app_group.find_file_by_path('App-Bridging-Header.h') || app_group.new_file('App-Bridging-Header.h')

# 3. Add Frameworks
frameworks_group = project.main_group.find_subpath('Frameworks', true)
python_xcf = frameworks_group.find_file_by_path('Python.xcframework') || frameworks_group.new_file('Frameworks/Python.xcframework')
target.frameworks_build_phase.add_file_reference(python_xcf)

# Embed Frameworks Phase
embed_phase = target.copy_files_build_phases.find { |p| p.name == 'Embed Frameworks' }
unless embed_phase
  embed_phase = project.new(Xcodeproj::Project::Object::PBXCopyFilesBuildPhase)
  embed_phase.name = 'Embed Frameworks'
  embed_phase.symbolic_path = :frameworks
  target.build_phases << embed_phase
end
build_file = embed_phase.add_file_reference(python_xcf)
build_file.settings = { 'ATTRIBUTES' => ['CodeSignOnCopy', 'RemoveHeadersOnCopy'] }

# 4. Add Resource Folders (as directory references to preserve hierarchy) & Dylib
['python', 'python_app'].each do |folder_name|
  folder_path = "App/#{folder_name}"
  ref = app_group.find_file_by_path(folder_name)
  unless ref
    ref = app_group.new_reference(folder_path)
    ref.last_known_file_type = 'folder'
  end
  target.resources_build_phase.add_file_reference(ref) unless target.resources_build_phase.files_references.include?(ref)
end

['libswisseph.dylib'].each do |dylib_name|
  dylib_path = "App/#{dylib_name}"
  ref = app_group.find_file_by_path(dylib_name) || app_group.new_reference(dylib_path)
  target.resources_build_phase.add_file_reference(ref) unless target.resources_build_phase.files_references.include?(ref)
end

project.save
puts "Successfully patched App.xcodeproj for embedded Python & libswisseph!"
