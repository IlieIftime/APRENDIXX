#!/usr/bin/env ruby
# Add the small audited native bridge to Briefcase's generated Xcode target.

require "fileutils"
require "pathname"
require "xcodeproj"

root = Pathname.new(File.expand_path("../..", __dir__))
project_path = Dir[root.join("build", "aprendix", "iOS", "*.xcodeproj")].first
abort "Briefcase iOS Xcode project was not found" unless project_path

project = Xcodeproj::Project.open(project_path)
target = project.targets.find { |candidate| candidate.name.casecmp("Aprendix").zero? }
target ||= project.targets.first
abort "Aprendix Xcode target was not found" unless target

native_dir = Pathname.new(project_path).dirname.join("Native")
FileUtils.mkdir_p(native_dir)
%w[AprendixKeychainBridge.h AprendixKeychainBridge.m].each do |name|
  FileUtils.cp(root.join("mobile", "ios", name), native_dir.join(name))
end

group = project.main_group.find_subpath("Native", true)
group.set_source_tree("<group>")
group.set_path("Native")
implementation = group.files.find { |file| file.path == "AprendixKeychainBridge.m" }
implementation ||= group.new_file("AprendixKeychainBridge.m")
header = group.files.find { |file| file.path == "AprendixKeychainBridge.h" }
header ||= group.new_file("AprendixKeychainBridge.h")
unless target.source_build_phase.files_references.include?(implementation)
  target.source_build_phase.add_file_reference(implementation, true)
end

frameworks = project.frameworks_group
%w[Security.framework UserNotifications.framework UIKit.framework].each do |name|
  reference = frameworks.files.find { |file| file.path&.end_with?(name) }
  reference ||= frameworks.new_file("System/Library/Frameworks/#{name}", "SDKROOT")
  unless target.frameworks_build_phase.files_references.include?(reference)
    target.frameworks_build_phase.add_file_reference(reference, true)
  end
end

project.save
puts "Integrated native Keychain, notifications, and haptics bridge into #{project_path}"
