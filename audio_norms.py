import subprocess
import json
import sys
import os
import argparse


def loudnorm_normalization(file_name):

    base_file_name, extension = file_name.split(".")

    file_stats_file = os.path.join("stats_pass", f"{base_file_name}_stats.json")
    # only do 1st pass if we already don't have the stats for it
    if not os.path.isfile(file_stats_file):
        stats_log = os.path.join("stats_pass", f"{base_file_name}.log")
        # only really do 1st pass if we don't have the output file (because JSON generation and 1st pass are 2 different steps)l in
        if not os.path.isfile(stats_log):
            print(
                f"Starting loudnorm 1st pass for '{file_name}'... Writing to '{stats_log}'"
            )
            command = f'ffmpeg.exe -hide_banner -y -i "{file_name}" -c:v copy -pass 1 -af loudnorm=print_format=json -f null /dev/null 2>&1 | tee "{stats_log}"'

            stats_p = subprocess.run([command], shell=True)

        # generate the json stats file

        print("Generating Json file")
        valid_json_lines = []
        # json_info
        with open(stats_log, "r") as f:
            for line in f:
                if "{" in line:
                    valid_json_lines.append("{\n")
                    valid_json_lines += f.readlines()

        with open(file_stats_file, "w") as f_stats:
            f_stats.writelines(valid_json_lines)
        # helpful print after successful write
        print("".join(valid_json_lines))

    # do 2nd pass

    norm_out = os.path.join("normalized", f"{base_file_name}_normalized.{extension}")
    norm_log = os.path.join("normalized", f"{base_file_name}_normalized.log")
    with open(file_stats_file, "r") as j:
        audio_stats = json.load(j)
        # print stats again because why not
        print("Using values: ")
        print(audio_stats)

        measured_i = audio_stats["input_i"]
        measured_lra = audio_stats["input_lra"]
        measured_tp = audio_stats["input_tp"]
        measured_thresh = audio_stats["input_thresh"]
        offset = audio_stats["target_offset"]
        print(
            f"Starting loudnorm 2nd pass for '{file_name}'... Writing to '{norm_out}'"
        )

        second_command = f'ffmpeg.exe -hide_banner -i "{file_name}" -c:v copy -c:a aac -pass 2 -af loudnorm=measured_I={measured_i}:measured_LRA={measured_lra}:measured_tp={measured_tp}:measured_thresh={measured_thresh}:offset={offset} "{norm_out}" 2>&1 | tee "{norm_log}"'

        norm_p = subprocess.run(second_command, shell=True, text=True)


def volume_detect(path_to_file) -> str:
    file_folder, file_name = os.path.split(path_to_file)
    base_name, _ = file_name.split(".")
    detect_log = os.path.join(file_folder, f"{base_name}_detect.log")

    command = f'ffmpeg.exe  -hide_banner -i "{path_to_file}" -af "volumedetect" -vn -sn -dn -f null /dev/null 2>&1 | tee "{detect_log}"'
    subprocess.run([command], shell=True, text=True)
    return detect_log


def change_volume(path_to_file, value):
    _, file_name = os.path.split(path_to_file)
    base_name, extension = file_name.split(".")
    command = f'ffmpeg.exe  -hide_banner -i "{path_to_file}"  -c:v copy -c:a aac -af "volume={value}dB" "{base_name}_sound.{extension}"'
    subprocess.run([command], shell=True, text=True)


if __name__ == "__main__":
    if sys.platform == "win32":
        print(
            "Windows is not supported because stuff with subprocess that i can't be asked to figure out, just run on linux (or if you want, check comments of code"
        )
        # Check this thread for a potential implementation of tee behaviour using subprocess https://stackoverflow.com/a/11688535
        exit(1)
    elif sys.platform == "linux":
        parser = argparse.ArgumentParser()
        parser.add_argument("video", help="Video on which to perform actions")
        parser.add_argument(
            "-vd", "--detect", help="Applies 'volumedetect' filter", action="store_true"
        )
        parser.add_argument(
            "-l", "--loudnorm", help="Performs 2-pass loudnorm", action="store_true"
        )
        parser.add_argument(
            "-vi",
            "--volume",
            nargs="?",
            const=False,
            help="Increases volume level by provided dB value",
        )

        args = parser.parse_args()

        file_name = args.video
        detected_file = None
        print(args)
        if args.detect:
            detected_file = volume_detect(file_name)
        if args.loudnorm:
            loudnorm_normalization(file_name)

        if args.volume is not None:
            if args.volume:
                if args.detect:
                    print(
                        f"WARNING: Both '-vd' and {args.volume} provided, using only value '{args.volume}' instead of reading from generated '-vd' file!"
                    )

                change_volume(file_name, args.volume)
            else:
                # args.volume == False , so only option was provided, no value
                if not args.detect:
                    sys.exit(
                        "No value provided! If you wish to adjust automatically to 0dB, please pass the '-vd' ('--volume') argument as well!"
                    )
                else:
                    print(
                        f"WARNING: '-vd' passed, reading value from file at '{detected_file}'"
                    )
                    line_value = None
                    with open(detected_file, "r") as volume_file:
                        for line in volume_file:
                            # format is always something like
                            # [Parsed_volumedetect_0 @ 000002125af2f7c0] max_volume: [-|+]XX.XX dB
                            if "] max_volume:" in line:
                                line_value = line.split(":")[1]
                                break
                    if line_value is None:
                        sys.exit("Unable to read from file! Exiting...")
                    # format is always something like " [-|+]XX.XX dB", splitting by spaces gets us the numeric value
                    volume_change = float(line_value.split(" ")[1])
                    # if values only differ by something around 0.3dB, difference is negligible, so ignore it. So, we cast it float to make that comparison, and also because it's easier to invert
                    if abs(volume_change) <= 0.3:
                        print(
                            f"Difference too small ({volume_change}) to change, exiting succesfully..."
                        )
                        exit()
                    else:
                        print(
                            f"Value of {volume_change} read, increasing/decreasing accordingly"
                        )
                        # pass the inverse value, so for negatives volume will be increased, positives volume with be decreased  (in order to try and approach the max_volume 0.0dB desired)
                        change_volume(file_name, -volume_change)
    else:
        print(sys.platform, " not tested, please edit the code and try manually")
