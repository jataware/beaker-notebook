import html2canvas from 'html2canvas';
import { Document, Packer, Paragraph, ImageRun, LevelFormat, HeadingLevel, TextRun, AlignmentType, convertInchesToTwip, Table, TableRow, TableCell, TableLayoutType } from 'docx';
import type { IImageOptions, INumberingOptions } from 'docx';

export class DocumentExporter {

  private getNumberingConfig(): INumberingOptions {
    return {
      config: [
        {
          reference: "bullet-list",
          levels: [
            {
              level: 0,
              format: LevelFormat.BULLET,
              text: "•",
              alignment: AlignmentType.LEFT,
              style: {
                paragraph: {
                  indent: { left: convertInchesToTwip(0.5), hanging: convertInchesToTwip(0.25) },
                },
              },
            },
            {
              level: 1,
              format: LevelFormat.BULLET,
              text: "◦",
              alignment: AlignmentType.LEFT,
              style: {
                paragraph: {
                  indent: { left: convertInchesToTwip(1), hanging: convertInchesToTwip(0.25) },
                },
              },
            },
          ],
        },
        {
          reference: "numbered-list",
          levels: [
            {
              level: 0,
              format: LevelFormat.DECIMAL,
              text: "%1.",
              alignment: AlignmentType.LEFT,
              style: {
                paragraph: {
                  indent: { left: convertInchesToTwip(0.5), hanging: convertInchesToTwip(0.25) },
                },
              },
            },
            {
              level: 1,
              format: LevelFormat.LOWER_LETTER,
              text: "%2.",
              alignment: AlignmentType.LEFT,
              style: {
                paragraph: {
                  indent: { left: convertInchesToTwip(1), hanging: convertInchesToTwip(0.25) },
                },
              },
            },
          ],
        },
      ],
    };
  }

  async captureImages(container: HTMLElement): Promise<string[]> {
    const images = container.querySelectorAll('img');
    const imagePromises: Promise<string | null>[] = [];

    images.forEach(img => {
      imagePromises.push(this.captureImageAsBase64(img));
    });

    const results = await Promise.all(imagePromises);
    return results.filter(result => result !== null) as string[];
  }

  private async captureImageAsBase64(img: HTMLImageElement): Promise<string | null> {
    try {
      const canvas = await html2canvas(img, {
        useCORS: true,
        allowTaint: true,
        backgroundColor: null,
        scale: 1,
        logging: false,
      });
      return canvas.toDataURL('image/png');
    } catch (error) {
      console.error('Error capturing image:', error);
      return null;
    }
  }

  private getDocumentStyles() {
    return {
      paragraphStyles: [
        {
          id: "Normal",
          name: "Normal",
          basedOn: "Normal",
          next: "Normal",
          run: {
            font: "Calibri",
            size: 22,
          },
          paragraph: {
            spacing: {
              before: 120,
              after: 120,
            },
          },
        },
        {
          id: "ListParagraph",
          name: "List Paragraph",
          basedOn: "Normal",
          run: {
            font: "Calibri",
            size: 22,
          },
          paragraph: {
            spacing: {
              before: 60,
              after: 60,
            },
          },
        },
      ],
    };
  }

  async exportToDocx(elementDOM: HTMLElement, title: string): Promise<void> {
    const doc = new Document({
      numbering: this.getNumberingConfig(),
      styles: this.getDocumentStyles(),
      sections: [{
        properties: {},
        children: [
          new Paragraph({
            children: [
              new TextRun({
                text: title,
                font: "Calibri",
                size: 32,
                bold: true,
              }),
            ],
            heading: HeadingLevel.TITLE,
            spacing: { after: 300 },
          }),
          
          ...(await this.htmlToDocxParagraphs(elementDOM)),
        ],
      }],
    });

    const blob = await Packer.toBlob(doc);
    this.downloadBlob(blob, `${title}.docx`);
  }

  private async htmlToDocxParagraphs(contentDiv: HTMLElement): Promise<(Paragraph | Table)[]> {
    const elements: (Paragraph | Table)[] = [];

    for (const element of Array.from(contentDiv.children)) {
      await this.processElement(element, elements);
    }

    return elements;
  }

  private async processElement(element: Element, elements: (Paragraph | Table)[]): Promise<void> {
    const tagName = element.tagName.toLowerCase();

    switch (tagName) {
      case 'h1':
        const h1Text = this.extractTextFromElement(element);
        if (h1Text.trim()) {
          elements.push(new Paragraph({
            children: [
              new TextRun({
                text: h1Text,
                font: "Calibri",
                size: 32,
                bold: true,
                color: "263238",
              }),
            ],
            heading: HeadingLevel.HEADING_1,
            spacing: { before: 480, after: 240 },
          }));
        }
        break;

      case 'h2':
        const h2Text = this.extractTextFromElement(element);
        if (h2Text.trim()) {
          elements.push(new Paragraph({
            children: [
              new TextRun({
                text: h2Text,
                font: "Calibri",
                size: 30,
                bold: true,
                color: "37474F",
              }),
            ],
            heading: HeadingLevel.HEADING_2,
            spacing: { before: 360, after: 180 },
          }));
        }
        break;

      case 'h3':
        const h3Text = this.extractTextFromElement(element);
        if (h3Text.trim()) {
          elements.push(new Paragraph({
            children: [
              new TextRun({
                text: h3Text,
                font: "Calibri",
                size: 26,
                bold: true,
                color: "455A64",
              }),
            ],
            heading: HeadingLevel.HEADING_3,
            spacing: { before: 240, after: 120 },
          }));
        }
        break;

      case 'ul':
        this.processListElement(element, elements, true, 0);
        break;

      case 'ol':
        this.processListElement(element, elements, false, 0);
        break;

      case 'table':
        this.processTableElement(element, elements);
        break;

      case 'img':
        await this.processImageElement(element as HTMLImageElement, elements);
        break;

      case 'p':
        // Check if paragraph contains images (common with markdown-rendered images)
        const imagesInParagraph = element.querySelectorAll('img');
        if (imagesInParagraph.length > 0) {
          // Process all images in the paragraph
          for (const img of Array.from(imagesInParagraph)) {
            await this.processImageElement(img as HTMLImageElement, elements);
          }
          // Then process any remaining text content (excluding images)
          const textContent = element.cloneNode(true) as Element;
          const imgClones = textContent.querySelectorAll('img');
          imgClones.forEach(img => img.remove());
          const textRuns = this.extractFormattedTextRuns(textContent);
          if (textRuns.length > 0) {
            elements.push(new Paragraph({
              children: textRuns,
              style: "Normal",
              spacing: { before: 120, after: 120 }
            }));
          }
        } else {
          // No image, process as normal paragraph
          const textRuns = this.extractFormattedTextRuns(element);
          if (textRuns.length > 0) {
            elements.push(new Paragraph({
              children: textRuns,
              style: "Normal",
              spacing: { before: 120, after: 120 }
            }));
          }
        }
        break;

      default:
        if (element.children.length > 0) {
          for (const child of Array.from(element.children)) {
            await this.processElement(child, elements);
          }
        }
        break;
    }
  }

  private processTableElement(tableElement: Element, elements: (Paragraph | Table)[]): void {
    const rows: TableRow[] = [];
    
    const tbody = tableElement.querySelector('tbody');
    const thead = tableElement.querySelector('thead');
    
    const firstRow = tableElement.querySelector('tr');
    let columnCount = 0;
    if (firstRow) {
      columnCount = firstRow.querySelectorAll('th, td').length;
    }
    
    if (thead) {
      const headerRows = thead.querySelectorAll('tr');
      headerRows.forEach(row => {
        const cells = row.querySelectorAll('th, td');
        const tableCells: TableCell[] = [];
        
        cells.forEach(cell => {
          // headers: use simpler approach that allows bold formatting
          const cellText = this.extractTextFromElement(cell);
          const cellRuns = this.createFormattedCellRuns(cell, true); // true = bold headers
          
          tableCells.push(new TableCell({
            children: [new Paragraph({
              children: cellRuns.length > 0 ? cellRuns : [new TextRun({
                text: cellText,
                font: "Calibri",
                size: 22,
                bold: true,
              })],
            })],
          }));
        });
        
        if (tableCells.length > 0) {
          rows.push(new TableRow({
            children: tableCells,
          }));
        }
      });
    }
    
    if (tbody) {
      const bodyRows = tbody.querySelectorAll('tr');
      bodyRows.forEach(row => {
        const cells = row.querySelectorAll('th, td');
        const tableCells: TableCell[] = [];
        
        cells.forEach(cell => {
          const cellRuns = this.createFormattedCellRuns(cell, false); // false = not bold
          
          tableCells.push(new TableCell({
            children: [new Paragraph({
              children: cellRuns.length > 0 ? cellRuns : [new TextRun({
                text: this.extractTextFromElement(cell),
                font: "Calibri",
                size: 22,
              })],
            })],
          }));
        });
        
        if (tableCells.length > 0) {
          rows.push(new TableRow({
            children: tableCells,
          }));
        }
      });
    }
    
    if (rows.length > 0) {
      const table = new Table({
        rows: rows,
        columnWidths: Array(columnCount).fill(5000),
        margins: {
          top: 200,
          bottom: 200,
        },
      });
      elements.push(table);
    }
  }

  private async processImageElement(imgElement: HTMLImageElement, elements: (Paragraph | Table)[]): Promise<void> {
    try {
      const imageData = await this.captureImageAsBase64(imgElement);
      if (imageData) {
        const imageBuffer = this.base64ToBuffer(imageData);
        
        const img = new Image();
        img.src = imageData;
        
        await new Promise((resolve) => {
          img.onload = resolve;
        });

        const originalWidth = img.width;
        const originalHeight = img.height;
        const aspectRatio = originalWidth / originalHeight;
        
        const maxWidth = 600;
        const maxHeight = 450;
        
        let finalWidth: number;
        let finalHeight: number;

        if (aspectRatio > maxWidth / maxHeight) {
          finalWidth = maxWidth;
          finalHeight = maxWidth / aspectRatio;
        } else {
          finalHeight = maxHeight;
          finalWidth = maxHeight * aspectRatio;
        }

        elements.push(new Paragraph({
          children: [
            new ImageRun({
              data: imageBuffer,
              transformation: {
                width: finalWidth,
                height: finalHeight,
              },
            } as IImageOptions),
          ],
          spacing: { before: 200, after: 200 },
        }));
      }
    } catch (error) {
      console.error('Error processing image:', error);
      elements.push(new Paragraph({
        children: [
          new TextRun({
            text: `[Image could not be processed: ${imgElement.src}]`,
            font: "Calibri",
            size: 22,
            italics: true,
          }),
        ],
      }));
    }
  }

  private extractTextFromElement(element: Element): string {
    return element.textContent?.trim() || '';
  }

  private extractFormattedTextRuns(element: Element): TextRun[] {
    const textRuns: TextRun[] = [];
    this.processTextNodes(element, textRuns);
    return textRuns;
  }

  private createFormattedCellRuns(element: Element, forceBold: boolean = false): TextRun[] {
    const textRuns: TextRun[] = [];
    this.processCellTextNodes(element, textRuns, forceBold);
    return textRuns;
  }

  private processCellTextNodes(node: Node, textRuns: TextRun[], forceBold: boolean): void {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent || '';
      if (text.trim()) {
        textRuns.push(new TextRun({
          text: text,
          font: "Calibri",
          size: 22,
          bold: forceBold,
        }));
      }
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      const element = node as Element;
      const tagName = element.tagName.toLowerCase();

      if (tagName === 'br') {
        textRuns.push(new TextRun({
          text: '',
          break: 1,
        }));
        return;
      }

      const text = element.textContent || '';
      if (text.trim() && (tagName === 'strong' || tagName === 'b' || tagName === 'em' || tagName === 'i')) {
        const isBold = forceBold || tagName === 'strong' || tagName === 'b';
        const isItalic = tagName === 'em' || tagName === 'i';

        textRuns.push(new TextRun({
          text: text,
          font: "Calibri",
          size: 22,
          bold: isBold,
          italics: isItalic,
        }));
      } else {
        Array.from(element.childNodes).forEach(child => {
          this.processCellTextNodes(child, textRuns, forceBold);
        });
      }
    }
  }

  private processTextNodes(node: Node, textRuns: TextRun[]): void {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = node.textContent || '';
      if (text.trim()) {
        textRuns.push(new TextRun({
          text: text,
          font: "Calibri",
          size: 22,
        }));
      }
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      const element = node as Element;
      const tagName = element.tagName.toLowerCase();

      if (tagName === 'br') {
        textRuns.push(new TextRun({
          text: '',
          break: 1,
        }));
        return;
      }

      const text = element.textContent || '';
      if (text.trim() && (tagName === 'strong' || tagName === 'b' || tagName === 'em' || tagName === 'i')) {
        const isBold = tagName === 'strong' || tagName === 'b';
        const isItalic = tagName === 'em' || tagName === 'i';

        textRuns.push(new TextRun({
          text: text,
          font: "Calibri",
          size: 22,
          bold: isBold,
          italics: isItalic,
        }));
      } else {
        Array.from(element.childNodes).forEach(child => {
          this.processTextNodes(child, textRuns);
        });
      }
    }
  }

  private processListElement(listElement: Element, elements: (Paragraph | Table)[], isBulletList: boolean, level: number = 0): void {
    const numberingReference = isBulletList ? "bullet-list" : "numbered-list";
    let isFirstListItem = true;
    
    Array.from(listElement.children).forEach((li) => {
      if (li.tagName.toLowerCase() === 'li') {
        const text = this.extractTextFromListItem(li);
        if (text.trim()) {
          elements.push(new Paragraph({
            children: [
              new TextRun({
                text: text,
                font: "Calibri",
                size: 22,
              }),
            ],
            style: "ListParagraph",
            numbering: {
              reference: numberingReference,
              level: level,
            },
            spacing: { 
              before: isFirstListItem ? 240 : 60,
              after: 60
            }
          }));
          isFirstListItem = false;
        }

        const nestedLists = li.querySelectorAll(':scope > ul, :scope > ol');
        nestedLists.forEach(nestedList => {
          const isNestedBullet = nestedList.tagName.toLowerCase() === 'ul';
          const shouldUseBullets = !isBulletList && isNestedBullet;
          this.processListElement(
            nestedList as Element, 
            elements, 
            shouldUseBullets, 
            shouldUseBullets ? 0 : level + 1
          );
        });
      }
    });
  }

  private extractTextFromListItem(li: Element): string {
    const clone = li.cloneNode(true) as Element;
    const nestedLists = clone.querySelectorAll('ul, ol');
    nestedLists.forEach(list => list.remove());
    return this.extractTextFromElement(clone);
  }

  private base64ToBuffer(base64: string): Uint8Array {
    const base64Data = base64.split(',')[1];
    const binaryString = window.atob(base64Data);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes;
  }

  private downloadBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
}