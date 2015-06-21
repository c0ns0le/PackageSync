import sublime
import sublime_plugin
import os
import tempfile
import fnmatch
import time
import shutil
import zipfile
import json
import sys


def load_settings():
    s = sublime.load_settings("PackageSync.sublime-settings")

    global sync_settings
    sync_settings = {
        "prompt_for_location": s.get("prompt_for_location", False),
        "list_backup_path": s.get("list_backup_path", ""),
        "zip_backup_path": s.get("zip_backup_path", ""),
        "folder_backup_path": s.get("folder_backup_path", ""),
        "ignore_files": s.get("ignore_files", []) + ["PackageSync.sublime-settings"],
        "include_files": s.get("include_files", []),
        "ignore_dirs": s.get("ignore_dirs", [])
    }


def init_paths():
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")

    #: Path of file to be used when backing up to or restoring from the sublime-settings file for Package Control
    global default_list_backup_path
    default_list_backup_path = os.path.join(
        desktop_path, "SublimePackagesList.txt")

    #: Path of the installed "/packages/user/" folder to backup or restore
    global user_settings_folder
    user_settings_folder = os.path.join(sublime.packages_path(), "User")

    #: Path to be used when backing up to or restoring from the "/packages/user" folder as a folder
    global default_folder_backup_path
    default_folder_backup_path = os.path.join(
        desktop_path, "SublimePackagesBackup")

    #: Path to be used when backing up to or restoring from the "/packages/user" folder as a zip file
    global default_zip_backup_path
    default_zip_backup_path = os.path.join(
        desktop_path, "SublimePackagesBackup.zip")


def install_new_packages():
    try:
        # Remove the last-run file in order to trigger the package installation
        pkg_control_last_run = os.path.join(
            sublime.packages_path(), "User", "Package Control.last-run")
        if os.path.isfile(pkg_control_last_run):
            os.remove(pkg_control_last_run)

        # Import packageControlCleaner
        pkg_control_cleanup = sys.modules[
            "Package Control.package_control.package_cleanup"]
        pkg_control_cleanup.PackageCleanup().start()
    except Exception as e:
        print(
            "PackageSync: Error while installing packages via Package Control.")
        raise e


def packagesync_cancelled():
    print("PackageSync: Backup/Restore operation cancelled")


def create_temp_backup():
    temp_backup_folder = os.path.join(tempfile.gettempdir(), str(time.time()))
    shutil.copytree(user_settings_folder, temp_backup_folder)

    for root, dir_names, file_names in os.walk(temp_backup_folder):
        for dir in dir_names:
            if dir in sync_settings["ignore_dirs"]:
                shutil.rmtree(os.path.join(root, dir), True)

        for file_name in file_names:
            absolute_path = os.path.join(root, file_name)
            relative_path = os.path.relpath(absolute_path, temp_backup_folder)

            include_matches = [
                fnmatch.fnmatch(relative_path, p) for p in sync_settings["include_files"]]
            ignore_matches = [
                fnmatch.fnmatch(relative_path, p) for p in sync_settings["ignore_files"]]

            if any(ignore_matches) or not any(include_matches):
                os.remove(absolute_path)

    return temp_backup_folder


def backup_with_prompt_on_done(path):
    global prompt_parameters

    if os.path.exists(path) is True:
        confirm_override = sublime.yes_no_cancel_dialog(
            "Backup already exists @ %s \nOverride it?" % path)

        if confirm_override is sublime.DIALOG_YES:
            prompt_parameters["operation_to_perform"](path)

        elif confirm_override is sublime.DIALOG_NO:
            prompt_parameters["initial_text"] = path
            prompt_for_location()

        else:
            prompt_parameters["operation_to_perform"](None)

    elif os.path.isabs(os.path.dirname(path)) is True:
        prompt_parameters["operation_to_perform"](path)

    else:
        sublime.error_message("Please provide a valid path for backup.")
        prompt_parameters["initial_text"] = path
        prompt_for_location()


def restore_with_prompt_on_done(path):
    global prompt_parameters

    if os.path.exists(path) is True:
        if prompt_parameters["type"] is "file" and os.path.isfile(path) is True:
            prompt_parameters["operation_to_perform"](path)

        elif prompt_parameters["type"] is "folder" and os.path.isdir(path) is True:
            prompt_parameters["operation_to_perform"](path)

        else:
            sublime.error_message("Please provide a valid path for backup.")
            prompt_parameters["initial_text"] = path
            prompt_for_location()

    else:
        sublime.error_message("Please provide a valid path for backup.")
        prompt_parameters["initial_text"] = path
        prompt_for_location()


def prompt_for_location():
    if prompt_parameters["mode"] is "backup":
        prompt_parameters["window_context"].show_input_panel("Backup Path", prompt_parameters[
                                                             "initial_text"], backup_with_prompt_on_done, None, packagesync_cancelled)
    elif prompt_parameters["mode"] is "restore":
        prompt_parameters["window_context"].show_input_panel("Backup Path", prompt_parameters[
                                                             "initial_text"], restore_with_prompt_on_done, None, packagesync_cancelled)


def backup_pkg_list(backup_path):
    if backup_path is not None:
        try:
            package_control_settings = sublime.load_settings(
                "Package Control.sublime-settings")
            installed_packages = package_control_settings.get(
                "installed_packages") or []

            if os.path.isfile(backup_path):
                os.remove(backup_path)
            elif not os.path.exists(os.path.dirname(backup_path)):
                os.makedirs(os.path.dirname(backup_path))

            with open(backup_path, "w") as _backupFile:
                json.dump(
                    {"installed_packages": installed_packages}, _backupFile)

            print("PackageSync: Backup of installed packages list created at %s" %
                  backup_path)
        except Exception as e:
            print(
                "PackageSync: Error while backing up installed packages list")
            raise e
    else:
        packagesync_cancelled()


class BackupInstalledPackagesListCommand(sublime_plugin.WindowCommand):

    def run(self):
        """ Backup the sublime-settings file for Package Control.
        This file contains the list of installed packages.
        The backup is stored on the backup location with the name specified in the
        config file. """

        init_paths()
        load_settings()

        if sync_settings["prompt_for_location"] is False:
            list_backup_path = sync_settings["list_backup_path"]

            try:
                if list_backup_path is "":
                    backup_path = default_list_backup_path
                elif os.path.exists(list_backup_path):
                    if sublime.ok_cancel_dialog("Backup already exists @ %s \nOverride it?" % list_backup_path) is True:
                        os.remove(list_backup_path)
                        backup_path = list_backup_path
                    else:
                        backup_path = None
                elif os.path.isabs(os.path.dirname(list_backup_path)):
                    backup_path = list_backup_path
                else:
                    sublime.error_message(
                        "Invalid path provided in user-settings. Please correct & then retry.")
                    backup_path = None
            except Exception as e:
                print("PackageSync: Error while fetching backup path.")
                raise e

            backup_pkg_list(backup_path)
        else:
            global prompt_parameters
            prompt_parameters = {
                "mode": "backup",
                "type": "file",
                "window_context": self.window,
                "initial_text": default_list_backup_path,
                "operation_to_perform": backup_pkg_list,
                "on_change": None,
                "on_cancel": packagesync_cancelled
            }
            prompt_for_location()


def restore_pkg_list(backup_path):
    if backup_path is not None:
        try:
            print("PackageSync: Restoring package list from %s" % backup_path)
            with open(backup_path, "r") as f:
                _installed_packages = json.load(f)["installed_packages"]

                _package_control_settings = sublime.load_settings(
                    "Package Control.sublime-settings")
                _package_control_settings.set(
                    "installed_packages", _installed_packages)
                sublime.save_settings("Package Control.sublime-settings")

            install_new_packages()

        except Exception as e:
            print(
                "PackageSync: Error while restoring packages from package list")
            raise e
    else:
        packagesync_cancelled()


class RestoreInstalledPackagesListCommand(sublime_plugin.WindowCommand):

    def run(self):
        """ Restore the sublime-settings file for Package Control.
        This file contains the list of installed packages.
        The backup file should be stored on the backup location with the name
        specified in the config file. """

        init_paths()
        load_settings()

        if sync_settings["prompt_for_location"] is False:
            list_backup_path = sync_settings["list_backup_path"]

            try:
                if list_backup_path is "":
                    backup_path = default_list_backup_path
                elif os.path.isfile(list_backup_path):
                    backup_path = list_backup_path
                else:
                    sublime.error_message(
                        "Invalid path provided in user-settings. Please correct & then retry.")
                    backup_path = None
            except Exception as e:
                print("PackageSync: Error while fetching backup path.")
                raise e

            restore_pkg_list(backup_path)
        else:
            global prompt_parameters
            prompt_parameters = {
                "mode": "restore",
                "type": "file",
                "window_context": self.window,
                "initial_text": default_list_backup_path,
                "operation_to_perform": restore_pkg_list,
                "on_change": None,
                "on_cancel": packagesync_cancelled
            }
            prompt_for_location()


def backup_folder(backup_path):
    if backup_path is not None:
        try:
            if os.path.isdir(backup_path):
                shutil.rmtree(backup_path, True)

            temp_backup_folder = create_temp_backup()
            shutil.copytree(temp_backup_folder, backup_path)
            print("PackageSync: Backup of packages & settings created at %s" %
                  backup_path)
        except Exception as e:
            print("PackageSync: Error while backing up packages to folder")
            raise e
    else:
        packagesync_cancelled()


class BackupPackagesToFolderCommand(sublime_plugin.WindowCommand):

    def run(self):
        """ Backup the "/Packages/User" folder to the backup location.
        This backs up the sublime-settings file created by user settings.
        Package Control settings file is also inherently backed up. """

        init_paths()
        load_settings()

        if sync_settings["prompt_for_location"] is False:
            folder_backup_path = sync_settings["folder_backup_path"]

            try:
                if folder_backup_path is "":
                    backup_path = default_folder_backup_path
                elif os.path.exists(folder_backup_path) and len(os.listdir(folder_backup_path)) > 0:
                    if sublime.ok_cancel_dialog("Backup already exists @ %s \nOverride it?" % folder_backup_path) is True:
                        backup_path = folder_backup_path
                    else:
                        backup_path = None
                elif os.path.isabs(os.path.dirname(folder_backup_path)):
                    backup_path = folder_backup_path
                else:
                    sublime.error_message(
                        "Invalid path provided in user-settings. Please correct & then retry.")
                    backup_path = None
            except Exception as e:
                print("PackageSync: Error while fetching backup path.")
                raise e

            backup_folder(backup_path)
        else:
            global prompt_parameters
            prompt_parameters = {
                "mode": "backup",
                "type": "folder",
                "window_context": self.window,
                "initial_text": default_folder_backup_path,
                "operation_to_perform": backup_folder,
                "on_change": None,
                "on_cancel": packagesync_cancelled
            }
            prompt_for_location()


def restore_folder(backup_path):
    if backup_path is not None:
        try:
            print(
                "PackageSync: Restoring package list & user settings from %s" % backup_path)
            shutil.rmtree(user_settings_folder)
            shutil.copytree(
                default_folder_backup_path, user_settings_folder)

            install_new_packages()

        except Exception as e:
            print(
                "PackageSync: Error while restoring packages from folder")
            raise e
    else:
        packagesync_cancelled()


class RestorePackagesFromFolderCommand(sublime_plugin.WindowCommand):

    def run(self):
        """ Restore the "/Packages/User" folder from the backup location.
        This restores the sublime-settings file created by user settings.
        Package Control settings file is also inherently restored. """

        init_paths()
        load_settings()

        if sync_settings["prompt_for_location"] is False:
            folder_backup_path = sync_settings["folder_backup_path"]

            try:
                if folder_backup_path is "":
                    backup_path = default_folder_backup_path
                elif os.path.isdir(folder_backup_path):
                    backup_path = folder_backup_path
                else:
                    sublime.error_message(
                        "Invalid path provided in user-settings. Please correct & then retry.")
                    backup_path = None
            except Exception as e:
                print("PackageSync: Error while fetching backup path.")
                raise e

            restore_folder(backup_path)
        else:
            global prompt_parameters
            prompt_parameters = {
                "mode": "restore",
                "type": "folder",
                "window_context": self.window,
                "initial_text": default_folder_backup_path,
                "operation_to_perform": restore_folder,
                "on_change": None,
                "on_cancel": packagesync_cancelled
            }
            prompt_for_location()


def backup_zip(backup_path):
    if backup_path is not None:
        try:
            temp_zip_file_path = os.path.join(
                tempfile.gettempdir(), str(time.time()))
            temp_backup_folder = create_temp_backup()

            shutil.make_archive(temp_zip_file_path, "zip", temp_backup_folder)

            if os.path.isfile(backup_path):
                os.remove(backup_path)
            elif not os.path.exists(os.path.dirname(backup_path)):
                os.makedirs(os.path.dirname(backup_path))
            shutil.move(temp_zip_file_path + ".zip", backup_path)

            print("PackageSync: Zip backup of packages & settings created at %s" %
                  backup_path)
        except Exception as e:
            print("PackageSync: Error while backing up packages to zip file")
            raise e
    else:
        packagesync_cancelled()


class BackupPackagesToZipCommand(sublime_plugin.WindowCommand):

    def run(self):
        """ Backup the "/Packages/User" folder to the backup location.
        This backs up the sublime-settings file created by user settings.
        Package Control settings file is also inherently backed up. """

        init_paths()
        load_settings()

        if sync_settings["prompt_for_location"] is False:
            zip_backup_path = sync_settings["zip_backup_path"]

            try:
                if zip_backup_path is "":
                    backup_path = default_zip_backup_path
                elif os.path.exists(zip_backup_path):
                    if sublime.ok_cancel_dialog("Backup already exists @ %s \nOverride it?" % zip_backup_path) is True:
                        os.remove(zip_backup_path)
                        backup_path = zip_backup_path
                    else:
                        backup_path = None
                elif os.path.isabs(os.path.dirname(zip_backup_path)):
                    backup_path = zip_backup_path
                else:
                    sublime.error_message(
                        "Invalid path provided in user-settings. Please correct & then retry.")
                    backup_path = None
            except Exception as e:
                print("PackageSync: Error while fetching backup path.")
                raise e

            backup_zip(backup_path)
        else:
            global prompt_parameters
            prompt_parameters = {
                "mode": "backup",
                "type": "file",
                "window_context": self.window,
                "initial_text": default_zip_backup_path,
                "operation_to_perform": backup_zip,
                "on_change": None,
                "on_cancel": packagesync_cancelled
            }
            prompt_for_location()


def restore_zip(backup_path):
    if backup_path is not None:
        try:
            print(
                "PackageSync: Restoring package list & user settings from %s" % backup_path)

            shutil.rmtree(user_settings_folder)
            with zipfile.ZipFile(backup_path, "r") as z:
                z.extractall(user_settings_folder)

            install_new_packages()

        except Exception as e:
            print(
                "PackageSync: Error while restoring packages from zip file")
            raise e
    else:
        packagesync_cancelled()


class RestorePackagesFromZipCommand(sublime_plugin.WindowCommand):

    def run(self):
        """ Restore the "/Packages/User" folder from the backup location.
        This restores the sublime-settings file created by user settings.
        Package Control settings file is also inherently restored. """

        init_paths()
        load_settings()

        if sync_settings["prompt_for_location"] is False:
            zip_backup_path = sync_settings["zip_backup_path"]

            try:
                if zip_backup_path is "":
                    backup_path = default_zip_backup_path
                elif os.path.isfile(zip_backup_path):
                    backup_path = zip_backup_path
                else:
                    sublime.error_message(
                        "Invalid path provided in user-settings. Please correct & then retry.")
                    backup_path = None
            except Exception as e:
                print("PackageSync: Error while fetching backup path.")
                raise e

            restore_zip(backup_path)
        else:
            global prompt_parameters
            prompt_parameters = {
                "mode": "restore",
                "type": "file",
                "window_context": self.window,
                "initial_text": default_zip_backup_path,
                "operation_to_perform": restore_zip,
                "on_change": None,
                "on_cancel": packagesync_cancelled
            }
            prompt_for_location()
