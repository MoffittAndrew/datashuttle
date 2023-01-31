import copy
from collections import UserDict
from collections.abc import ItemsView, KeysView, ValuesView
from pathlib import Path
from typing import Any, Optional, Union, cast

import yaml

from datashuttle.configs import canonical_configs, canonical_directories
from datashuttle.utils import directories, utils


class Configs(UserDict):
    """
    Class to hold the datashuttle configs.

    The configs must match exactly the standard set
    in canonical_configs.py. If updating these configs,
    this should be done through changing canonical_configs.py

    The input dict is checked that it conforms to the
    canonical standard by calling check_dict_values_raise_on_fail()

    project_name and all paths are set at runtime but not stored.

    Parameters
    ----------

    file_path :
        full filepath to save the config .yaml file to.

    input_dict :
        a dict of config key-value pairs to input dict.
        This must contain all canonical_config keys
    """

    def __init__(
        self, project_name: str, file_path: Path, input_dict: Union[dict, None]
    ) -> None:
        super(Configs, self).__init__(input_dict)

        self.project_name = project_name
        self.file_path = file_path

        self.keys_str_on_file_but_path_in_class = [
            "local_path",
            "remote_path",
        ]
        self.sub_prefix = "sub-"
        self.ses_prefix = "ses-"

        self.top_level_dir_name: str  # TODO: these are set in datashuttpe.py. Should be set in configs!

        self.data_type_dirs: dict
        self.logging_path: Path
        self.hostkeys_path: Path
        self.ssh_key_path: Path
        self.project_metadata_path: Path

    def setup_after_load(self) -> None:
        self.convert_str_and_pathlib_paths(self, "str_to_path")
        self.check_dict_values_raise_on_fail()

    def check_dict_values_raise_on_fail(self) -> None:
        """
        Check the values of the current dictionary are set
        correctly and will not cause downstream errors.

        This will raise an error if the dictionary
        does not match the canonical keys and value types.
        """
        canonical_configs.check_dict_values_raise_on_fail(self)

    def keys(self) -> KeysView:
        return self.data.keys()

    def items(self) -> ItemsView:
        return self.data.items()

    def values(self) -> ValuesView:
        return self.data.values()

    # -------------------------------------------------------------------------
    # Save / Load from file
    # -------------------------------------------------------------------------

    def dump_to_file(self) -> None:
        """
        Save the dictionary to .yaml file stored in self.file_path.
        """
        cfg_to_save = copy.deepcopy(self.data)
        self.convert_str_and_pathlib_paths(cfg_to_save, "path_to_str")

        with open(self.file_path, "w") as config_file:
            yaml.dump(cfg_to_save, config_file, sort_keys=False)

    def load_from_file(self) -> None:
        """
        Load a config dict saved at .yaml file. Note this will
        not automatically check the configs are valid, this
        requires calling self.check_dict_values_raise_on_fail()
        """
        with open(self.file_path, "r") as config_file:
            config_dict = yaml.full_load(config_file)

        self.convert_str_and_pathlib_paths(config_dict, "str_to_path")

        self.data = config_dict

    # -------------------------------------------------------------------------
    # Update Configs
    # -------------------------------------------------------------------------

    def update_an_entry(self, option_key: str, new_info: Any) -> None:
        """
        Convenience function to update individual entry of configuration
        file. The config file, and currently loaded self.cfg will be
        updated.

        In case an update is breaking, set to new value,
        test validity and revert if breaking change.

        Parameters
        ----------

        option_key : dictionary key of the option to change,
            see make_config_file()

        new_info : value to update the config too
        """
        if option_key not in self:
            utils.log_and_raise_error(f"'{option_key}' is not a valid config.")

        original_value = copy.deepcopy(self[option_key])

        if option_key in self.keys_str_on_file_but_path_in_class:
            new_info = Path(new_info)

        self[option_key] = new_info

        check_change = self.safe_check_current_dict_is_valid()

        if check_change["passed"]:
            self.dump_to_file()
            utils.log_and_message(
                f"{option_key} has been updated to {new_info}"
            )

            if option_key in ["connection_method", "remote_path"]:
                if self["connection_method"] == "ssh":
                    utils.log_and_message(
                        f"SSH will be used to connect to project directory at: {self['remote_path']}"
                    )
                elif self["connection_method"] == "local_filesystem":
                    utils.log_and_message(
                        f"Local filesystem will be used to connect to project "
                        f"directory at: {self['remote_path'].as_posix()}"
                    )
        else:
            self[option_key] = original_value
            utils.log_and_raise_error(
                f"\n{check_change['error']}\n{option_key} was not updated"
            )

    def safe_check_current_dict_is_valid(self) -> dict:
        """
        Check the dict, but do not raise error as
        we need to set the putatively changed key
        back to the state before change attempt.

        Propagate the error message so it can be
        shown later.
        """
        try:
            self.check_dict_values_raise_on_fail()
            return {"passed": True, "error": None}
        except BaseException as e:
            return {"passed": False, "error": str(e)}

    # --------------------------------------------------------------------
    # Utils
    # --------------------------------------------------------------------

    def convert_str_and_pathlib_paths(
        self, config_dict: Union["Configs", dict], direction: str
    ) -> None:
        """
        Config paths are stored as str in the .yaml but used as Path
        in the module, so make the conversion here.

        Parameters
        ----------

        config_dict : DataShuttle.cfg dict of configs
        direction : "path_to_str" or "str_to_path"
        """
        for path_key in self.keys_str_on_file_but_path_in_class:
            value = config_dict[path_key]

            if value:
                if direction == "str_to_path":
                    config_dict[path_key] = Path(value)

                elif direction == "path_to_str":
                    if type(value) != str:
                        config_dict[path_key] = value.as_posix()

                else:
                    utils.log_and_raise_error(
                        "Option must be 'path_to_str' or 'str_to_path'"
                    )

    def make_path(self, base: str, subdirs: Union[str, list]) -> Path:
        """
        Function for joining relative path to base dir.
        If path already starts with base dir, the base
        dir will not be joined.

        Parameters
        ----------

        base: "local", "remote" or "datashuttle"

        subdirs: a list (or string for 1) of
            directory names to be joined into a path.
            If file included, must be last entry (with ext).
        """
        if isinstance(subdirs, list):
            subdirs_str = "/".join(subdirs)
        else:
            subdirs_str = cast(str, subdirs)

        subdirs_path = Path(subdirs_str)

        base_dir = self.get_base_dir(base)

        if utils.path_already_stars_with_base_dir(base_dir, subdirs_path):
            joined_path = subdirs_path
        else:
            joined_path = base_dir / subdirs_path

        return joined_path

    def get_base_dir(self, base: str) -> Path:
        """
        Convenience function to return the full base path.

        Parameters
        ----------

        base : base path, "local", "remote" or "datashuttle"

        """
        if base == "local":
            base_dir = self["local_path"] / self.top_level_dir_name
        elif base == "remote":
            base_dir = self["remote_path"] / self.top_level_dir_name
        elif base == "datashuttle":
            base_dir, __ = utils.get_datashuttle_path(self.project_name)
        return base_dir

    def get_rclone_config_name(
        self, connection_method: Optional[str] = None
    ) -> str:
        """
        Convenience function to get the rclone config
        name (these configs are created by datashuttle
        but managed and stored by rclone).
        """
        if connection_method is None:
            connection_method = self["connection_method"]

        return f"remote_{self.project_name}_{connection_method}"

    def make_rclone_transfer_options(self, dry_run: bool, exclude_list: str):
        return {
            "overwrite_old_files": self["overwrite_old_files"],
            "transfer_verbosity": self["transfer_verbosity"],
            "show_transfer_progress": self["show_transfer_progress"],
            "dry_run": dry_run,
            "exclude_list": exclude_list,
        }

    def init_paths(self):
        """"""
        self.project_metadata_path = self["local_path"] / ".datashuttle"

        self.ssh_key_path = self.make_path(
            "datashuttle", self.project_name + "_ssh_key"
        )

        self.hostkeys_path = self.make_path("datashuttle", "hostkeys")

        self.logging_path = self.make_and_get_logging_path()

    def make_and_get_logging_path(self) -> Path:
        """
        Currently logging is located in config path
        """
        logging_path = self.project_metadata_path / "logs"
        directories.make_dirs(logging_path)
        return logging_path

    def init_data_type_dirs(self):
        """"""
        self.data_type_dirs = canonical_directories.get_data_type_directories(
            self
        )

    def get_data_type_items(
        self, data_type: Union[str, list]
    ) -> Union[ItemsView, zip]:
        """
        Get the .items() structure of the data type, either all of
        them (stored in self.data_type_dirs) or as a single item.
        """
        if type(data_type) == str:
            data_type = [data_type]

        items: Union[ItemsView, zip]

        if "all" in data_type:
            items = self.data_type_dirs.items()
        else:
            items = zip(
                data_type,
                [self.data_type_dirs[key] for key in data_type],
            )

        return items

    def items_from_data_type_input(
        self,
        local_or_remote: str,
        data_type: Union[list, str],
        sub: str,
        ses: Optional[str] = None,
    ) -> Union[ItemsView, zip]:
        """
        Get the list of data_types to transfer, either
        directly from user input, or by searching
        what is available if "all" is passed.

        Parameters
        ----------

        see _transfer_data_type() for parameters.
        """
        base_dir = self.get_base_dir(local_or_remote)

        if data_type not in [
            "all",
            ["all"],
            "all_data_type",
            ["all_data_type"],
        ]:  # TODO: make this better
            data_type_items = self.get_data_type_items(
                data_type,
            )
        else:
            data_type_items = directories.search_data_dirs_sub_or_ses_level(
                self,
                base_dir,
                local_or_remote,
                sub,
                ses,
            )

        return data_type_items

    def get_sub_or_ses_prefix(self, sub_or_ses: str) -> str:
        """
        Get the sub / ses prefix (default is "sub-" and "ses-") set in cfgs.
        These should always be "sub-" or "ses-" by SWC-BIDS.
        """
        if sub_or_ses == "sub":
            prefix = self.sub_prefix
        elif sub_or_ses == "ses":
            prefix = self.ses_prefix
        return prefix
