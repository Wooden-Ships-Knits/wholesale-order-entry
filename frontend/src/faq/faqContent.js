// THE FAQ CONTENT. This is the file to edit — FaqPage.jsx renders whatever is
// here and needs no changes when questions are added, removed or reordered.
//
// Shape:
//   sections: [{ title, items: [{ q, a }] }]
//
// `a` may be a plain string, or an array of strings for several paragraphs.
// Order is the order shown; a section with no items is skipped rather than
// rendering an empty heading.
//
// Keep answers short enough to read standing up. Anything that needs more than
// a paragraph or two is usually a sign the thing being explained should be
// clearer in the product instead.

export const FAQ_SECTIONS = [
  {
    title: 'Placing an order',
    items: [
      {
        q: 'Question goes here?',
        a: 'Answer goes here.',
      },
      {
        q: 'A question whose answer needs two paragraphs?',
        a: [
          'First paragraph.',
          'Second paragraph — pass an array and each entry becomes its own.',
        ],
      },
    ],
  },
  {
    title: 'Signing and payment',
    items: [
      {
        q: 'Question goes here?',
        a: 'Answer goes here.',
      },
    ],
  },
  {
    title: 'Shipping',
    items: [
      {
        q: 'Question goes here?',
        a: 'Answer goes here.',
      },
    ],
  },
]
