﻿# Run this as "python mk/update-travis-yml.py"

# Copyright 2015 Brian Smith.
#
# Permission to use, copy, modify, and/or distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND BRIAN SMITH AND THE AUTHORS DISCLAIM
# ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES
# OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL BRIAN SMITH OR THE AUTHORS
# BE LIABLE FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY
# DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN
# AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

import re
import shutil

rusts = [
    "stable",
    "nightly",
    "beta",
]

linux_compilers = [
    # Assume the default compiler is GCC. This is run first because it is the
    # one most likely to break, especially since GCC 4.6 is the default
    # compiler on Travis CI for Ubuntu 12.04, and GCC 4.6 is not supported by
    # BoringSSL.
    "",

    # Newest clang and GCC.
    "clang-5.0",

    "gcc-7",
]

# Clang 3.4 and GCC 4.6 are already installed by default.
linux_default_clang = "clang-3.4"

default_compilers = [
     "", # Don't set CC.'
]

compilers = {
    "i686-unknown-linux-gnu" : linux_compilers,
    "x86_64-unknown-linux-gnu" : linux_compilers,
}

feature_sets = [
    "",
]

modes = [
    "DEBUG",
    "RELWITHDEBINFO"
]

# Mac OS X is first because we don't want to have to wait until all the Linux
# configurations have been built to find out that there is a failure on Mac.
oss = [
    "osx",
    "linux",
]

targets = {
    "osx" : [
        "x86_64-apple-darwin",
    ],
    "linux" : [
        "armv7-linux-androideabi",
        "x86_64-unknown-linux-gnu",
        "aarch64-unknown-linux-gnu",
        "i686-unknown-linux-gnu",
        "arm-unknown-linux-gnueabihf",
        "mips64-unknown-linux-gnuabi64",
        "mips64el-unknown-linux-gnuabi64",
        "mipsel-unknown-linux-gnu",
        "mips-unknown-linux-gnu"
    ],
}

def format_entries():
    return "\n".join([format_entry(os, target, compiler, rust, mode, features)
                      for rust in rusts
                      for os in oss
                      for target in targets[os]
                      for compiler in compilers.get(target, default_compilers)
                      for mode in modes
                      for features in feature_sets])

# We use alternative names (the "_X" suffix) so that, in mk/travis.sh, we can
# enure that we set the specific variables we want and that no relevant
# variables are unintentially inherited into the build process. Also, we have
# to set |CC_X| instead of |CC| since Travis sets |CC| to its Travis CI default
# value *after* processing the |env:| directive here.
entry_template = """
    - env: TARGET_X=%(target)s %(compilers)s FEATURES_X=%(features)s MODE_X=%(mode)s KCOV=%(kcov)s
      rust: %(rust)s
      os: %(os)s"""

entry_indent = "      "

entry_services_template = """
      services:
        %(services)s"""

entry_packages_template = """
      addons:
        apt:
          packages:
            %(packages)s"""

entry_sources_template = """
          sources:
            %(sources)s"""

def format_entry(os, target, compiler, rust, mode, features):
    # Currently kcov only runs on Linux.
    #
    # GCC 5 was picked arbitrarily to restrict coverage report to one build for
    # efficiency reasons.
    #
    # Cargo passes RUSTFLAGS to rustc only in Rust 1.9 and later. When Rust 1.9
    # is released then we can change this to run (also) on the stable channel.
    #
    # DEBUG mode is needed because debug symbols are needed for coverage
    # tracking.
    kcov = (os == "linux" and compiler == "gcc-5" and rust == "nightly" and
            mode == "DEBUG")

    target_words = target.split("-")
    arch = target_words[0]
    vendor = target_words[1]
    sys = target_words[2]

    if sys == "darwin":
        abi = sys
        sys = "macos"
    elif sys == "androideabi":
        abi = sys
        sys = "linux"
    else:
        abi = target_words[3]

    def prefix_all(prefix, xs):
        return [prefix + x for x in xs]

    template = entry_template

    if sys == "linux":
        packages = sorted(get_linux_packages_to_install(target, compiler, arch, kcov))
        sources_with_dups = sum([get_sources_for_package(p) for p in packages],[])
        sources = sorted(list(set(sources_with_dups)))
        services = sorted(list(set(get_services_for_arch(arch))))
    else:
        services = []

    # TODO: Use trusty for everything?
    if arch in ["aarch64", "arm", "armv7"]:
        template += """
      dist: trusty
      sudo: required"""

    if sys == "linux":
        if services:
            template += entry_services_template
        if packages:
            template += entry_packages_template
        if sources:
            template += entry_sources_template
    else:
        packages = []
        sources = []

    cc = get_cc(sys, compiler)

    if os == "osx":
        os += "\n" + entry_indent + "osx_image: xcode9.3"

    compilers = []
    if cc != "":
        compilers += ["CC_X=" + cc]
    compilers += ""

    return template % {
            "compilers": " ".join(compilers),
            "features" : features,
            "mode" : mode,
            "kcov": "1" if kcov == True else "0",
            "packages" : "\n            ".join(prefix_all("- ", packages)),
            "rust" : rust,
            "sources" : "\n            ".join(prefix_all("- ", sources)),
            "target" : target,
            "os" : os,
            "services" : "\n            ".join(prefix_all("- ", services)),
            }

def get_linux_packages_to_install(target, compiler, arch, kcov):
    if compiler in ["", linux_default_clang]:
        packages = []
    elif compiler.startswith("clang-") or compiler.startswith("gcc-"):
        packages = [compiler]
    else:
        packages = []

    if arch == "i686":
        if kcov == True:
            packages += ["libcurl3:i386",
                         "libcurl4-openssl-dev:i386",
                         "libdw-dev:i386",
                         "libelf-dev:i386",
                         "libkrb5-dev:i386",
                         "libssl-dev:i386"]

        if compiler.startswith("clang-") or compiler == "":
            packages += ["libc6-dev-i386",
                         "gcc-multilib"]
        elif compiler.startswith("gcc-"):
            packages += [compiler + "-multilib",
                         "linux-libc-dev:i386"]
        else:
            raise ValueError("unexpected compiler: %s" % compiler)
    elif arch == "x86_64":
        if kcov == True:
            packages += ["libcurl4-openssl-dev",
                         "libelf-dev",
                         "libdw-dev",
                         "binutils-dev"]

    return packages

def get_services_for_arch(arch):
    if arch not in ('i686', 'x86_64'):
        return ['docker']
    return []

def get_sources_for_package(package):
    ubuntu_toolchain = "ubuntu-toolchain-r-test"
    if package.startswith("clang-"):
        _, version = package.split("-")
        llvm_toolchain = "llvm-toolchain-trusty-%s" % version

        # Stuff in llvm-toolchain-trusty depends on stuff in the toolchain
        # packages.
        return [llvm_toolchain, ubuntu_toolchain]
    else:
        return [ubuntu_toolchain]

def get_cc(sys, compiler):
    if sys == "linux" and compiler == linux_default_clang:
        return "clang"

    return compiler

def main():
    # Make a backup of the file we are about to update.
    shutil.copyfile(".travis.yml", ".travis.yml~")
    with open(".travis.yml", "r+b") as file:
        begin = "    # BEGIN GENERATED\n"
        end = "    # END GENERATED\n"
        old_contents = file.read()
        new_contents = re.sub("%s(.*?)\n[ ]*%s" % (begin, end),
                              "".join([begin, format_entries(), "\n\n", end]),
                              old_contents, flags=re.S)
        if old_contents == new_contents:
            print "No changes"
            return

        file.seek(0)
        file.write(new_contents)
        file.truncate()
        print new_contents

if __name__ == '__main__':
    main()
