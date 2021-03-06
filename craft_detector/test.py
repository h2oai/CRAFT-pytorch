"""
Copyright (c) 2019-present NAVER Corp.
MIT License
"""

# -*- coding: utf-8 -*-
import argparse
import cv2
import numpy as np
import os
import time
import torch
import torch.nn as nn
import torch.backends.cudnn as cudnn

from collections import OrderedDict
from torch.autograd import Variable

from .craft import CRAFT
from .craft_utils import get_det_boxes, adjust_result_coordinates
from .file_utils import get_files, save_result
from .imgproc import resize_aspect_ratio, normalize_mean_variance, cvt_to_heatmap, load_image
from .refinenet import RefineNet


def copy_state_dict(state_dict):
    if list(state_dict.keys())[0].startswith("module"):
        start_idx = 1
    else:
        start_idx = 0
    new_state_dict = OrderedDict()
    for k, v in state_dict.items():
        name = ".".join(k.split(".")[start_idx:])
        new_state_dict[name] = v
    return new_state_dict


def str2bool(v):
    return v.lower() in ("yes", "y", "true", "t", "1")


def arguments():
    parser = argparse.ArgumentParser(description='craft_text Text Detection')
    parser.add_argument('--trained_model', default='weights/craft_mlt_25k.pth', type=str, help='pretrained model')
    parser.add_argument('--text_threshold', default=0.7, type=float, help='text confidence threshold')
    parser.add_argument('--low_text', default=0.4, type=float, help='text low-bound score')
    parser.add_argument('--link_threshold', default=0.4, type=float, help='link confidence threshold')
    parser.add_argument('--cuda', default=True, type=str2bool, help='Use cuda for inference')
    parser.add_argument('--canvas_size', default=1280, type=int, help='image size for inference')
    parser.add_argument('--mag_ratio', default=1.5, type=float, help='image magnification ratio')
    parser.add_argument('--poly', default=False, action='store_true', help='enable polygon type')
    parser.add_argument('--show_time', default=False, action='store_true', help='show processing time')
    parser.add_argument('--test_folder', default='/data/', type=str, help='folder path to input images')
    parser.add_argument('--refine', default=False, action='store_true', help='enable link refiner')
    parser.add_argument('--refiner_model', default='weights/craft_refiner_CTW1500.pth', type=str,
                        help='pretrained refiner model')
    args = parser.parse_args(args=[])
    return args


def test_net(net, image, text_threshold, link_threshold, low_text, cuda, poly, refine_net=None):
    args = arguments()
    t0 = time.time()

    # resize
    img_resized, target_ratio, size_heatmap = resize_aspect_ratio(image,
                                                                  args.canvas_size,
                                                                  interpolation=cv2.INTER_LINEAR,
                                                                  mag_ratio=args.mag_ratio)
    ratio_h = ratio_w = 1 / target_ratio

    # pre-processing
    x = normalize_mean_variance(img_resized)
    x = torch.from_numpy(x).permute(2, 0, 1)  # [h, w, c] to [c, h, w]
    x = Variable(x.unsqueeze(0))  # [c, h, w] to [b, c, h, w]
    if cuda:
        x = x.cuda()

    # forward pass
    with torch.no_grad():
        y, feature = net(x)

    # make score and link map
    score_text = y[0, :, :, 0].cpu().data.numpy()
    score_link = y[0, :, :, 1].cpu().data.numpy()

    # refine link
    if refine_net is not None:
        with torch.no_grad():
            y_refiner = refine_net(y, feature)
        score_link = y_refiner[0, :, :, 0].cpu().data.numpy()

    t0 = time.time() - t0
    t1 = time.time()

    # Post-processing
    boxes, polys = get_det_boxes(score_text, score_link, text_threshold, link_threshold, low_text, poly)

    # coordinate adjustment
    boxes = adjust_result_coordinates(boxes, ratio_w, ratio_h)
    polys = adjust_result_coordinates(polys, ratio_w, ratio_h)
    for k in range(len(polys)):
        if polys[k] is None: polys[k] = boxes[k]

    t1 = time.time() - t1

    # render results (optional)
    render_img = score_text.copy()
    render_img = np.hstack((render_img, score_link))
    ret_score_text = cvt_to_heatmap(render_img)

    if args.show_time:
        print("infer/postproc time : {:.3f}/{:.3f}".format(t0, t1))

    return boxes, polys, ret_score_text


def load_craftnet_model(model_path='',
                        cuda=False):
    args = arguments()
    if not model_path:
        model_path = args.trained_model
    net = CRAFT()
    if cuda:
        net.load_state_dict(copy_state_dict(torch.load(model_path)))
        net = net.cuda()
        net = nn.DataParallel(net)
        cudnn.benchmark = False
    else:
        net.load_state_dict(copy_state_dict(torch.load(model_path, map_location='cpu')))
    net.eval()
    return net


def load_refinenet_model(model_path='',
                         cuda=False):
    args = arguments()
    if not model_path:
        model_path = args.refiner_model
    refine_net = RefineNet()
    if cuda:
        refine_net.load_state_dict(copy_state_dict(torch.load(model_path)))
        refine_net = refine_net.cuda()
        refine_net = torch.nn.DataParallel(refine_net)
    else:
        refine_net.load_state_dict(copy_state_dict(torch.load(model_path, map_location='cpu')))
    refine_net.eval()
    args.poly = True
    return refine_net


def infer_batch():
    args = arguments()

    # Read input, setup result folder
    image_list, _, _ = get_files(args.test_folder)
    result_folder = './result/'
    if not os.path.isdir(result_folder):
        os.mkdir(result_folder)

    # load net
    net = CRAFT()  # initialize
    if args.cuda:
        net.load_state_dict(copy_state_dict(torch.load(args.trained_model)))
        net = net.cuda()
        net = torch.nn.DataParallel(net)
        cudnn.benchmark = False
    else:
        net.load_state_dict(copy_state_dict(torch.load(args.trained_model, map_location='cpu')))
    net.eval()

    # LinkRefiner
    refine_net = None
    if args.refine:
        refine_net = RefineNet()
        if args.cuda:
            refine_net.load_state_dict(copy_state_dict(torch.load(args.refiner_model)))
            refine_net = refine_net.cuda()
            refine_net = torch.nn.DataParallel(refine_net)
        else:
            refine_net.load_state_dict(copy_state_dict(torch.load(args.refiner_model, map_location='cpu')))

        refine_net.eval()
        args.poly = True


    # load data
    for k, image_path in enumerate(image_list):
        image = load_image(image_path)
        bboxes, polys, score_text = test_net(net, image,
                                             args.text_threshold, args.link_threshold, args.low_text,
                                             args.cuda, args.poly, refine_net)

        # save score text
        filename, file_ext = os.path.splitext(os.path.basename(image_path))
        mask_file = result_folder + "/res_" + filename + '_mask.jpg'
        cv2.imwrite(mask_file, score_text)
        save_result(image_path, image[:, :, ::-1], polys, dirname=result_folder)


if __name__ == '__main__':
    infer_batch()
