import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);

// jsdom has no <dialog> behaviour; give it the two methods the app uses
HTMLDialogElement.prototype.showModal ||= function (this: HTMLDialogElement) { this.setAttribute("open", ""); };
HTMLDialogElement.prototype.close ||= function (this: HTMLDialogElement) { this.removeAttribute("open"); };
