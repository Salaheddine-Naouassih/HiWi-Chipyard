#!/bin/bash
# setup_fftw.sh - Automates bare-metal FFTW cross-compilation and Makefile patching

echo "========================================"
echo " 1. Building Bare-Metal FFTW for RISC-V..."
echo "========================================"

# Download and extract
wget -qnc http://www.fftw.org/fftw-3.3.10.tar.gz
tar -xzf fftw-3.3.10.tar.gz
cd fftw-3.3.10

# Cross-compile with bare-metal/medany flags
./configure --host=riscv64-unknown-elf \
            CC=riscv64-unknown-elf-gcc \
            CFLAGS="-O2 -mcmodel=medany" \
            --disable-shared \
            --enable-static \
            --disable-threads \
            --disable-fortran

make -j$(nproc)

echo "========================================"
echo " 2. Patching Chipyard Environment..."
echo "========================================"

# Move the artifacts to the Chipyard tests directory
cp .libs/libfftw3.a ../chipyard/tests/
cp api/fftw3.h ../chipyard/tests/

# Define the target Makefile
MAKEFILE_PATH="../chipyard/tests/Makefile"

# Patch 1: Inject the medany flag into CFLAGS (if not already there)
if ! grep -q "\-mcmodel=medany" "$MAKEFILE_PATH"; then
    # Finds the line starting with "CFLAGS  =" and appends the flag to the end
    sed -i '/^CFLAGS  =/ s/$/ -mcmodel=medany/' "$MAKEFILE_PATH"
    echo " -> Injected -mcmodel=medany into CFLAGS"
else
    echo " -> CFLAGS already patched, skipping."
fi

# Patch 2: Inject the custom linker rule (if not already there)
if ! grep -q "fft_benchmark.riscv:" "$MAKEFILE_PATH"; then
    # We use printf here to guarantee a real hardware TAB character (\t) is written.
    # If we used echo, copy-pasting could turn it into spaces and break the Makefile!
    printf "\n# Custom override to enforce strict Linker Order for FFTW\n" >> "$MAKEFILE_PATH"
    printf "fft_benchmark.riscv: fft_benchmark.o \$(libgloss)\n" >> "$MAKEFILE_PATH"
    printf "\t\$(GCC) \$(LDFLAGS) $< -o \$@ -L. -lfftw3 -lm\n" >> "$MAKEFILE_PATH"
    echo " -> Injected custom FFTW linker rule"
else
    echo " -> Linker rule already exists, skipping."
fi

echo "========================================"
echo " SUCCESS: Environment completely automated!"
echo "========================================"