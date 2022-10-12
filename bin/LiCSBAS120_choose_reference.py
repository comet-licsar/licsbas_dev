#!/usr/bin/env python3

import numpy as np
import matplotlib.pyplot as plt
import os
import argparse
import LiCSBAS_io_lib as io_lib
import LiCSBAS_tools_lib as tools_lib
from matplotlib import cm


def block_sum(array, k):
    result = np.add.reduceat(np.add.reduceat(array, np.arange(0, array.shape[0], k), axis=0),
                             np.arange(0, array.shape[1], k), axis=1)
    return result


if __name__ == "__main__":

    parser = argparse.ArgumentParser(description="Detect coregistration error")
    parser.add_argument('-f', "--frame_dir", default="./", help="directory of LiCSBAS output of a particular frame")
    parser.add_argument('-g', '--GEOCml_dir', dest="unw_dir", default="GEOCml10GACOS", help="folder containing unw input")
    parser.add_argument('-t', '--ts_dir', dest="ts_dir", default="TS_GEOCml10GACOS", help="folder containing time series")
    parser.add_argument('-w', '--window_size', dest="win", default="5", type=float, help="Window size in km")
    args = parser.parse_args()

    ### Define directories
    ifgdir = os.path.abspath(os.path.join(args.frame_dir, args.unw_dir))
    tsadir = os.path.abspath(os.path.join(args.frame_dir, args.ts_dir))
    resultsdir = os.path.join(tsadir, 'results')
    infodir = os.path.join(tsadir, 'info')

    ### Get size
    mlipar = os.path.join(ifgdir, 'slc.mli.par')
    width = int(io_lib.get_param_par(mlipar, 'range_samples'))
    length = int(io_lib.get_param_par(mlipar, 'azimuth_lines'))
    print("\nSize         : {} x {}".format(width, length), flush=True)

    ### Get resolution
    dempar = os.path.join(ifgdir, 'EQA.dem_par')
    lattitude_resolution = float(io_lib.get_param_par(dempar, 'post_lat'))
    window_size = int(abs(args.win / 110 / lattitude_resolution) + 0.5)   # 110 km per degree latitude
    print("\nWindow size : ", window_size)

    #%% Read date, network information and size
    ### Get dates
    ifgdates = tools_lib.get_ifgdates(ifgdir)

    ### Read bad_ifg11 and rm_ifg
    bad_ifg11file = os.path.join(infodir, '11bad_ifg.txt')
    bad_ifg11 = io_lib.read_ifg_list(bad_ifg11file)

    ### Remove bad ifgs and images from list
    ifgdates = list(set(ifgdates)-set(bad_ifg11))
    ifgdates.sort()

    ### Start counting indices for choosing the reference
    n_unw = np.zeros((length, width), dtype=np.float32)
    n_coh = np.zeros((length, width), dtype=np.float32)
    n_con = np.zeros((length, width), dtype=np.float32)

    ### Accumulate through network (1)unw pixel counts, (2) coherence and (3) size of connected components
    for ifgd in ifgdates:
        # turn ifg into ones and zeros for non-nan and nan values
        unwfile = os.path.join(ifgdir, ifgd, ifgd+'.unw')
        unw = io_lib.read_img(unwfile, length, width)
        unw[unw == 0] = np.nan # Fill 0 with nan
        n_unw += ~np.isnan(unw) # Summing number of unnan unw

        # coherence values from 0 to 1
        ccfile = os.path.join(ifgdir, ifgd, ifgd + '.cc')
        coh = io_lib.read_img(ccfile, length, width, np.uint8)
        coh = coh.astype(np.float32) / 255  # keep 0 as 0 which represent nan values
        n_coh += coh

        # connected components in terms of component area (pixel count)
        confile = os.path.join(ifgdir, ifgd, ifgd+'.conncomp')
        con = io_lib.read_img(confile, length, width, np.uint8)
        # replace component index by component size. the first component is the 0th component, which should be of size 0
        uniq_components, pixel_counts = np.unique(con.flatten(), return_counts=True)
        for i, component in enumerate(uniq_components[1:]):
            con[con==component] = pixel_counts[i+1]
        n_con += con

        del unw, coh, con

    ### calculate block sum and normalise
    block_unw = block_sum(n_unw, window_size)
    block_coh = block_sum(n_coh, window_size)
    block_con = block_sum(n_con, window_size)
    block_unw = block_unw / np.max(block_unw)
    block_coh = block_coh / np.max(block_coh)
    block_con = block_con / np.max(block_con)

    ### calculate block standard deviation of height
    hgtfile = os.path.join(resultsdir, 'hgt')
    hgt = io_lib.read_img(hgtfile, length, width)
    block_mean_hgt = block_sum(hgt, window_size)/(window_size**2)
    repeat_block_mean_hgt = np.repeat(block_mean_hgt, window_size, axis=1)
    broadcast_mean_hgt = np.repeat(repeat_block_mean_hgt, window_size, axis=0)
    hgt_demean = hgt - broadcast_mean_hgt[:hgt.shape[0], :hgt.shape[1]]
    hgt_demean_square = hgt_demean ** 2
    block_rms_hgt = np.sqrt( block_sum(hgt_demean_square, window_size) / (window_size ** 2) )
    block_rms_hgt = block_rms_hgt / np.nanpercentile(block_rms_hgt, 95)

    # low_block_rms_hgt = np.nanpercentile(block_rms_hgt, 10)
    # block_rms_hgt[block_rms_hgt < low_block_rms_hgt] = low_block_rms_hgt

    # block_rms_hgt[block_rms_hgt == 0] = 0.001

    ### calculate proxy from 4 indices
    block_proxy = block_unw + block_coh + block_con - block_rms_hgt
    block_proxy = block_proxy / np.max(block_proxy)

    ### turn 0 to nan for plotting
    block_unw[block_unw == 0] = np.nan
    block_coh[block_coh == 0] = np.nan
    block_con[block_con == 0] = np.nan
    block_rms_hgt[block_rms_hgt == 0] = np.nan
    block_proxy[block_proxy == 0] = np.nan

    ### load example unw for plotting in block resolution
    unwfile = os.path.join(ifgdir, ifgd, ifgd + '.unw')
    unw = io_lib.read_img(unwfile, length, width)
    unw_example = block_sum(unw, window_size)
    unw_example[unw_example == 0] = np.nan

    # plot figure
    fig, ax = plt.subplots(2, 3, sharey='all', sharex='all')
    im_unw = ax[0, 0].imshow(block_unw, vmin=0, vmax=1)
    im_coh = ax[0, 1].imshow(block_coh, vmin=0, vmax=1)
    im_con = ax[1, 0].imshow(block_con, vmin=0, vmax=1)
    im_hgt = ax[1, 1].imshow(block_rms_hgt, vmin=0, vmax=1)
    # im_hgt = ax[1, 1].imshow(block_rms_hgt, vmin=0, vmax=2/window_size)
    im_proxy = ax[0, 2].imshow(block_proxy)
    im_example = ax[1, 2].imshow(unw_example, cmap=cm.RdBu)
    plt.colorbar(im_unw, ax=ax, orientation='horizontal')

    ax[0, 0].set_title("block_sum_unw")
    ax[0, 1].set_title("block_sum_coh")
    ax[1, 0].set_title("block_sum_comp_size")
    ax[1, 1].set_title("block_std_hgt")
    ax[0, 2].set_title("proxy")
    ax[1, 2].set_title("unw example")

    ## choose distance closer to center
    # proxy_thresh = np.nanpercentile(block_proxy, 99)
    # refys, refxs = np.where(block_proxy > proxy_thresh)
    # print(refys, refxs, block_proxy[block_proxy < proxy_thresh])
    # distance_to_center = np.sqrt(( refys - length/2) ** 2 +  (refxs - width/2) ** 2 )
    # print(distance_to_center)
    # nearest_to_center = np.min(distance_to_center)
    # index_nearest_to_center = np.where(distance_to_center == nearest_to_center)
    # refy = refys[index_nearest_to_center]
    # refx = refxs[index_nearest_to_center]
    # print(index_nearest_to_center, refy, refx)

    proxy_max = np.nanmax(block_proxy)
    refys, refxs = np.where(block_proxy == proxy_max)
    refy = refys[0]
    refx = refxs[0]
    ax[1, 2].scatter(refx, refy, s=3, c='red')
    ax[0, 2].scatter(refx, refy, s=3, c='red')
    ax[0, 0].scatter(refx, refy, s=3, c='red')
    ax[0, 1].scatter(refx, refy, s=3, c='red')
    ax[1, 0].scatter(refx, refy, s=3, c='red')
    ax[1, 1].scatter(refx, refy, s=3, c='red')

    fig.savefig(os.path.join(infodir, "120_reference.png"), dpi=300, bbox_inches='tight')

    # fig, ax = plt.subplots(1, 2)
    # ax[0].imshow(block_rms_hgt, vmin=0, vmax=1/window_size)
    # hgt[hgt==0] = np.nan
    # ax[1].imshow(hgt)
    # fig.savefig("height.png", dpi=300, bbox_inches='tight')

    # print reference point
    refx1s, refx2s, refy1s, refy2s = refx*window_size, (refx+1)*window_size, refy*window_size, (refy+1)*window_size
    print('Selected ref: {}:{}/{}:{}'.format(refx1s, refx2s, refy1s, refy2s), flush=True)

    ### Save ref
    refsfile = os.path.join(infodir, '120ref.txt')
    with open(refsfile, 'w') as f:
        print('{}:{}/{}:{}'.format(refx1s, refx2s, refy1s, refy2s), file=f)


